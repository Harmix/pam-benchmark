"""Sync HTTP client for the Pam API.

Endpoints exercised by the benchmark:
  - `POST /v1/auth/login`                                          (admin login)
  - `POST /v1/admin/create-account`                                (per-sample user)
  - `POST /v1/admin/users/{user_id}/tokens`                        (mint per-user token — debug reuse)
  - `DELETE /v1/admin/delete-account/{user_id}`                    (per-sample user)
  - `POST /v1/memory/process-generic-files/{user_id}`              (upload + kick off memory pipeline)
  - `GET  /v1/memory/get-memory-pipeline-status/{user_id}/{run_id}` (poll status)
  - `POST /v1/messages/stream`                                     (SSE chat — questions)

Auth model:
  - Steps 2-4 require a bearer token that belongs to ``{user_id}``.
    ``create_account`` mints that per-user token and ``_headers()`` prefers
    it over the admin token.
  - ``401`` from these endpoints triggers a single refresh-and-retry (handles
    token expiry mid memory build); a persistent ``401`` or any ``403`` is
    raised as ``PamAuthError`` so the polling loop fails fast rather than
    treating bad creds like a stuck ``pending`` job.
  - ``delete-account`` keeps using the admin token regardless of which
    per-user token is currently "current".

The client is intentionally synchronous; the async harness wraps calls with
`asyncio.to_thread`. SSE parsing is unchanged.
"""

from __future__ import annotations

import io
import json
import logging
import time
from typing import Any, ClassVar

import requests
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class PamAuthError(RuntimeError):
    """Pam returned 401/403 — fatal misconfiguration, not a transient error.

    Raised after a single refresh on 401, or immediately on 403 (the bearer
    token doesn't belong to ``{user_id}``). The memory-pipeline polling loop
    catches this explicitly and re-raises, so a misconfigured token fails fast
    instead of looking like a stuck ``pending`` job for ``MAX_CONSECUTIVE_POLL_ERRORS``
    iterations before propagating.
    """

    def __init__(self, status_code: int, url: str, body: str):
        self.status_code = status_code
        self.url = url
        self.body = body
        super().__init__(f"Pam auth failure (HTTP {status_code}) at {url}: {body[:300]}")


class PamClient:
    """Client for the Pam API.

    Requires an admin login to obtain a token before creating benchmark user
    accounts. Per-call 401s trigger a token refresh and one retry, mirroring
    the reference implementation.
    """

    MAX_FILES_PER_REQUEST = 5
    SSE_TIMEOUT = 600

    # Memory pipeline polling: seconds between status checks + how many
    # consecutive transient errors to tolerate before propagating.
    MEMORY_POLL_INTERVAL = 30
    MAX_CONSECUTIVE_POLL_ERRORS = 3

    _TRANSIENT_HTTP_ERRORS: ClassVar[tuple[type[BaseException], ...]] = (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
    )

    def __init__(self, api_host: str, api_key: str | None = None):
        self.host = api_host.rstrip("/")
        self.base_url = f"{self.host}/v1"
        self.session = requests.Session()
        # Harmix API key (server-side `HARMIX_API_KEY`). Only needed to mint a
        # per-user token for an existing user (debug mode); the normal run uses
        # the admin bearer + per-user tokens from create_account.
        self.api_key = api_key
        self.admin_token: str | None = None
        self.access_token: str | None = None
        self.user_id: int | None = None
        self._admin_email: str | None = None
        self._admin_password: str | None = None
        self._user_email: str | None = None
        self._user_password: str | None = None

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self.access_token:
            h["Authorization"] = f"Bearer {self.access_token}"
        elif self.admin_token:
            h["Authorization"] = f"Bearer {self.admin_token}"
        return h

    def _retrying(self) -> Retrying:
        return Retrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=15),
            retry=retry_if_exception_type(self._TRANSIENT_HTTP_ERRORS),
            reraise=True,
        )

    @staticmethod
    def _raise_for_auth(resp: requests.Response, url: str) -> None:
        # Distinct from generic HTTPError so the polling loop can fail fast on
        # bad creds (token missing / wrong user_id) instead of waiting out the
        # transient-error budget.
        if resp.status_code in (401, 403):
            raise PamAuthError(resp.status_code, url, resp.text)

    # --- 0. Admin login ----------------------------------------------------

    def login(self, email: str, password: str) -> str:
        """Authenticate and store the admin token."""
        self._admin_email = email
        self._admin_password = password
        for attempt in self._retrying():
            with attempt:
                resp = self.session.post(
                    f"{self.host}/v1/auth/login",
                    json={"email": email, "password": password},
                    timeout=180,
                )
        resp.raise_for_status()
        data = resp.json()
        self.admin_token = data["tokens"]["access_token"]
        return self.admin_token

    def _login_as(self, email: str, password: str) -> str:
        """Login with arbitrary credentials and return the access token."""
        for attempt in self._retrying():
            with attempt:
                resp = self.session.post(
                    f"{self.host}/v1/auth/login",
                    json={"email": email, "password": password},
                    timeout=180,
                )
        resp.raise_for_status()
        return resp.json()["tokens"]["access_token"]

    def refresh_token(self) -> None:
        """Refresh both admin and user tokens using stored credentials."""
        if self._admin_email and self._admin_password:
            logger.info("Refreshing Pam admin token")
            self.admin_token = self._login_as(self._admin_email, self._admin_password)
        if self._user_email and self._user_password:
            logger.info("Refreshing Pam user token")
            self.access_token = self._login_as(self._user_email, self._user_password)

    # --- 1. Account lifecycle ----------------------------------------------

    def create_account(
        self,
        email: str,
        password: str,
        name: str,
        company_name: str = "Acme Inc",
        position: str = "Engineer",
    ) -> dict[str, Any]:
        url = f"{self.base_url}/admin/create-account"
        body = {
            "email": email,
            "password": password,
            "name": name,
            "company_name": company_name,
            "position": position,
        }
        headers = {**self._headers(), "Content-Type": "application/json"}
        for attempt in self._retrying():
            with attempt:
                resp = self.session.post(url, json=body, headers=headers, timeout=180)
        if not resp.ok:
            logger.warning("Pam create_account failed: %s %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["tokens"]["access_token"]
        self.user_id = data["user"]["id"]
        self._user_email = email
        self._user_password = password
        return data

    def _admin_headers(self) -> dict[str, str]:
        # delete-account is an admin endpoint; once one per-user token has been
        # superseded by another, we can't rely on `_headers()`. Force the admin
        # token explicitly so deletes work no matter which user is "current".
        if self.admin_token:
            return {"Authorization": f"Bearer {self.admin_token}"}
        return {}

    def issue_user_tokens(self, user_id: int) -> str:
        """Mint a per-user access token for an EXISTING user and store it.

        Calls `POST /v1/admin/users/{user_id}/tokens` with the Harmix `api-key`
        header (not a bearer). Used by debug mode so chat/memory calls run as
        the reused user — `messages/stream` answers from whichever user the
        bearer belongs to, so the admin token would query the wrong memory.

        Returns the access token (also set on `self.access_token` /
        `self.user_id`).
        """
        if not self.api_key:
            raise RuntimeError(
                "issue_user_tokens requires an api_key (set PAM_API_KEY) — needed to "
                "mint a per-user token for --pam-debug-user-id reuse"
            )
        url = f"{self.base_url}/admin/users/{user_id}/tokens"
        headers = {"api-key": self.api_key}
        resp = self.session.post(url, headers=headers, timeout=120)
        self._raise_for_auth(resp, url)
        if not resp.ok:
            logger.warning("Pam issue_user_tokens failed: %s %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        data = resp.json()
        access_token = data["access_token"]
        self.access_token = access_token
        self.user_id = user_id
        return access_token

    def delete_account(self, user_id: int | None = None) -> None:
        """Delete the user and all of their records (the full wipe).

        The benchmark only calls this when ``--backup-memory`` is NOT set; when
        it is set the account is kept entirely (see `PamBaseline.cleanup_sample`)
        so it can be reused later via ``--pam-debug-user-id``.
        """
        uid = user_id if user_id is not None else self.user_id
        if uid is None:
            raise ValueError("delete_account requires a user_id")
        url = f"{self.base_url}/admin/delete-account/{uid}"
        resp = self.session.delete(url, headers=self._admin_headers(), timeout=180)
        if resp.status_code == 401:
            self.refresh_token()
            resp = self.session.delete(url, headers=self._admin_headers(), timeout=180)
        resp.raise_for_status()

    # --- 2. Process generic files → kick off memory pipeline --------------

    @staticmethod
    def _build_files_payload(
        batch: list[tuple[str, bytes]],
    ) -> list[tuple[str, tuple[str, io.BytesIO, str]]]:
        """Build a fresh `requests` multipart payload from `(name, bytes)` pairs.

        Each call wraps the bytes in a NEW `BytesIO`, so the payload can be
        rebuilt per HTTP attempt instead of reusing a stream that `requests`
        has already drained to EOF.
        """
        return [("files", (fname, io.BytesIO(fbytes), "text/plain")) for fname, fbytes in batch]

    def process_generic_files(self, file_tuples: list[tuple[str, bytes]]) -> list[str]:
        """Upload files and trigger memory creation in one shot per batch.

        Calls `POST /v1/memory/process-generic-files/{user_id}` once per batch
        of up to `MAX_FILES_PER_REQUEST` files. Each call returns a `run_id`
        for the kicked-off memory pipeline; we return the list of run_ids
        ready to be polled via `wait_for_memory`.
        """
        if self.user_id is None:
            raise RuntimeError(
                "process_generic_files requires user_id (call login + create_account first)"
            )

        url = f"{self.base_url}/memory/process-generic-files/{self.user_id}"
        run_ids: list[str] = []
        for batch_start in range(0, len(file_tuples), self.MAX_FILES_PER_REQUEST):
            batch = file_tuples[batch_start : batch_start + self.MAX_FILES_PER_REQUEST]

            # A fresh multipart payload per attempt — `requests` reads each file
            # stream to EOF while encoding the body, so reusing one BytesIO on
            # the retry would transmit an empty file (which the server then zips
            # as a zero-byte `*_conversation.json`).
            resp = self.session.post(
                url, headers=self._headers(), files=self._build_files_payload(batch), timeout=300
            )
            if resp.status_code == 401:
                # Token may have expired during a long memory build — refresh
                # once and retry. A second 401 (or any 403) means the bearer
                # genuinely doesn't authorize this user_id; fail fast.
                self.refresh_token()
                resp = self.session.post(
                    url,
                    headers=self._headers(),
                    files=self._build_files_payload(batch),
                    timeout=300,
                )
            self._raise_for_auth(resp, url)
            if not resp.ok:
                logger.warning(
                    "Pam process_generic_files failed: %s %s",
                    resp.status_code,
                    resp.text[:500],
                )
            resp.raise_for_status()
            data = resp.json()
            run_id = data.get("run_id")
            if not run_id:
                raise RuntimeError(f"process_generic_files: no run_id in response: {data!r}")
            run_ids.append(run_id)
        return run_ids

    # --- 3. Memory pipeline status polling --------------------------------

    def get_memory_pipeline_status(self, run_id: str, user_id: int | None = None) -> dict[str, Any]:
        """Single status check against `GET /v1/memory/get-memory-pipeline-status/...`.

        The endpoint returns the pipeline's real `run_status` directly as
        `status` (`pending` / `running` / `queued` / `completed` / `failed`).
        We surface that shape unchanged so the polling loop can branch on
        `status`.
        """
        uid = user_id if user_id is not None else self.user_id
        if uid is None:
            raise ValueError("get_memory_pipeline_status requires user_id")
        url = f"{self.base_url}/memory/get-memory-pipeline-status/{uid}/{run_id}"
        resp = self.session.get(url, headers=self._headers(), timeout=120)
        if resp.status_code == 401:
            self.refresh_token()
            resp = self.session.get(url, headers=self._headers(), timeout=120)
        # 401-after-refresh or any 403 → PamAuthError. Surfaced distinctly
        # from `{"status": "pending"}` so the polling loop fails fast.
        self._raise_for_auth(resp, url)
        resp.raise_for_status()
        return resp.json()

    def wait_for_memory(self, run_ids: list[str], user_id: int | None = None) -> None:
        """Poll each `run_id` until it reaches a terminal status.

        - `status == "completed"` → return success.
        - `status == "failed"`    → raise RuntimeError with stage/message.
        - anything else (`pending` or unknown) → keep polling.

        Tolerates up to `MAX_CONSECUTIVE_POLL_ERRORS` transient HTTP errors
        per run before propagating.
        """
        uid = user_id if user_id is not None else self.user_id
        if uid is None:
            raise ValueError("wait_for_memory requires user_id")
        for run_id in run_ids:
            self._wait_for_one(run_id, uid)

    def _wait_for_one(self, run_id: str, user_id: int) -> None:
        logger.info(
            "Pam memory pipeline polling: user_id=%s run_id=%s every %ss",
            user_id,
            run_id,
            self.MEMORY_POLL_INTERVAL,
        )
        start = time.time()
        consecutive_errors = 0
        while True:
            time.sleep(self.MEMORY_POLL_INTERVAL)

            try:
                status_resp = self.get_memory_pipeline_status(run_id, user_id=user_id)
                consecutive_errors = 0
            except PamAuthError:
                # Bad creds won't fix themselves by retrying — surface the
                # misconfiguration immediately instead of letting it look like
                # a stuck pipeline for MAX_CONSECUTIVE_POLL_ERRORS iterations.
                raise
            except Exception as e:
                consecutive_errors += 1
                elapsed_min = (time.time() - start) / 60
                logger.warning(
                    "Pam memory pipeline poll error [%.1fm] (%d/%d) run_id=%s: %r",
                    elapsed_min,
                    consecutive_errors,
                    self.MAX_CONSECUTIVE_POLL_ERRORS,
                    run_id,
                    e,
                )
                if consecutive_errors >= self.MAX_CONSECUTIVE_POLL_ERRORS:
                    raise
                continue

            # The endpoint returns the real run_status directly as `status`
            # (pending / running / queued / completed / failed).
            status = status_resp.get("status", "pending")
            elapsed_min = (time.time() - start) / 60
            logger.info(
                "Pam memory pipeline [%.1fm] run_id=%s status=%s",
                elapsed_min,
                run_id,
                status,
            )

            if status == "completed":
                return
            if status == "failed":
                err_stage = status_resp.get("error_stage", "unknown")
                err_msg = status_resp.get("error_message", "no details")
                raise RuntimeError(
                    f"Pam memory pipeline failed (run_id={run_id}, stage={err_stage}): {err_msg}"
                )
            # else: pending / running / queued / unknown — keep polling

    # --- 4. Chat (SSE) -----------------------------------------------------

    def send_message(self, prompt: str, conversation_id: str | None = None) -> tuple[str, int]:
        """Send a message and return ``(answer_text, injected_tokens)``.

        Pam may produce multiple assistant text turns separated by tool-use
        cycles. Only the final assistant text turn contains the actual answer.

        Turn tracking (matches the reference):
          - ``role "assistant"`` + ``content_new.type "text"`` → append to
            the current turn buffer.
          - ``role "tool_use"`` / ``role "tool_result"`` → save the current
            turn and start a fresh buffer (next assistant text is a new turn).
          - ``role "result"`` / ``event: stream_stopped`` → terminal, stop.
        """
        body = {"prompt": prompt, "conversation_id": conversation_id}
        url = f"{self.base_url}/messages/stream"
        resp = self.session.post(
            url,
            json=body,
            headers=self._headers(),
            stream=True,
            timeout=self.SSE_TIMEOUT,
        )
        if resp.status_code == 401:
            self.refresh_token()
            resp = self.session.post(
                url,
                json=body,
                headers=self._headers(),
                stream=True,
                timeout=self.SSE_TIMEOUT,
            )
        resp.raise_for_status()

        return self._parse_sse_stream(resp.iter_lines(decode_unicode=True))

    @staticmethod
    def _parse_sse_stream(lines: Any) -> tuple[str, int]:
        """Extract `(final_answer_text, injected_tokens)` from Pam's SSE stream.

        Split out from `send_message` so it can be unit-tested against
        captured byte streams without a live server.
        """
        all_turns: list[list[str]] = []
        current_turn: list[str] = []
        injected_tokens: int = 0

        for line in lines:
            if not line:
                continue
            if line.startswith("event: stream_stopped"):
                break
            if not line.startswith("data: "):
                continue

            try:
                payload = json.loads(line[len("data: ") :])
            except json.JSONDecodeError:
                continue

            if payload.get("type") == "resume_conversation":
                continue

            role = payload.get("role")
            if role == "assistant":
                content_new = payload.get("content_new", {})
                if content_new.get("type") == "text" and content_new.get("text"):
                    current_turn.append(content_new["text"])
            elif role in ("tool_use", "tool_result"):
                if current_turn:
                    all_turns.append(current_turn)
                    current_turn = []
            elif role == "result":
                usage = payload.get("usage") or {}
                injected_tokens = (
                    payload.get("injected_tokens") or usage.get("injected_tokens") or 0
                )
                break

        if current_turn:
            all_turns.append(current_turn)

        answer = "".join(all_turns[-1]) if all_turns else ""
        return answer, int(injected_tokens or 0)
