"""Sync HTTP client for the Pam API.

Ported from the reference `PAMClient` in
`pam-benchmark-main/tasks/memtrack/environment/run_memtrack_pam_v2.py` with:
  - Pam naming throughout (no "PAM" in strings/comments)
  - tenacity for retries (matches the rest of the harness; the reference used backoff)
  - `backup_workspace` dropped (Pam handles workspace backup server-side)

The client is intentionally synchronous; the async harness wraps calls with
`asyncio.to_thread`. Polling cadence and SSE parsing match the reference
verbatim so behavior on the Pam side is unchanged.
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


class PamClient:
    """Client for the Pam API.

    Requires an admin login to obtain a token before creating benchmark user
    accounts. Per-call 401s trigger a token refresh and one retry, mirroring
    the reference implementation.
    """

    MAX_FILES_PER_REQUEST = 5
    SSE_TIMEOUT = 600

    # Memory pipeline polling (kept identical to the reference)
    MEMORY_POLL_INTERVAL = 30  # seconds between status checks
    TERMINAL_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {"completed", "failed", "stopped", "cancelled"}
    )
    PIPELINE_TYPE = "benchmark_memory"
    MAX_CONSECUTIVE_POLL_ERRORS = 3

    _TRANSIENT_HTTP_ERRORS: ClassVar[tuple[type[BaseException], ...]] = (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
    )

    def __init__(self, api_host: str):
        self.host = api_host.rstrip("/")
        self.base_url = f"{self.host}/v1"
        self.session = requests.Session()
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

    def delete_account(self) -> None:
        url = f"{self.base_url}/admin/delete-account/{self.user_id}"
        resp = self.session.delete(url, headers=self._headers(), timeout=180)
        if resp.status_code == 401:
            self.refresh_token()
            resp = self.session.delete(url, headers=self._headers(), timeout=180)
        resp.raise_for_status()

    # --- 2. File upload ----------------------------------------------------

    def upload_generic_files(self, file_tuples: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
        """Upload files in batches of MAX_FILES_PER_REQUEST.

        Args:
            file_tuples: list of (filename, file_bytes) pairs.

        Returns:
            Aggregated list of upload-result dicts from the Pam API.
        """
        all_results: list[dict[str, Any]] = []
        for batch_start in range(0, len(file_tuples), self.MAX_FILES_PER_REQUEST):
            batch = file_tuples[batch_start : batch_start + self.MAX_FILES_PER_REQUEST]
            files_payload = [
                ("files", (fname, io.BytesIO(fbytes), "text/plain")) for fname, fbytes in batch
            ]
            resp = self.session.post(
                f"{self.base_url}/files/upload-generic/{self.user_id}",
                headers=self._headers(),
                files=files_payload,
                timeout=180,
            )
            resp.raise_for_status()
            all_results.extend(resp.json())
        return all_results

    # --- 3. Memory creation (async server-side pipeline) -------------------

    def trigger_memory_pipeline(self, max_files: int | None = None, batch_size: int = 500) -> str:
        """Start the async `benchmark_memory` pipeline and return the run_id."""
        url = f"{self.base_url}/memory/pipeline/{self.PIPELINE_TYPE}/run"
        body = {
            "sync_type": "initial",
            "params": {"max_files": max_files, "batch_size": batch_size},
        }
        kwargs = dict(
            params={"user_id": self.user_id},
            json=body,
            headers=self._headers(),
            timeout=180,
        )
        resp = self.session.post(url, **kwargs)
        if resp.status_code == 401:
            self.refresh_token()
            kwargs["headers"] = self._headers()
            resp = self.session.post(url, **kwargs)
        if resp.status_code not in (200, 202):
            logger.warning(
                "Pam trigger_memory_pipeline failed: %s %s",
                resp.status_code,
                resp.text[:500],
            )
        resp.raise_for_status()
        data = resp.json()
        return data["run_id"]

    def poll_memory_status(self) -> dict[str, Any]:
        """Get the current status of the Pam memory pipeline.

        Refreshes the auth token on 401 and retries once.
        """
        url = f"{self.base_url}/memory/pipeline/{self.PIPELINE_TYPE}/status"
        resp = self.session.get(
            url,
            params={"user_id": self.user_id},
            headers=self._headers(),
            timeout=120,
        )
        if resp.status_code == 401:
            self.refresh_token()
            resp = self.session.get(
                url,
                params={"user_id": self.user_id},
                headers=self._headers(),
                timeout=120,
            )
        resp.raise_for_status()
        return resp.json()

    def create_memory(self, max_files: int | None = None, batch_size: int = 500) -> dict[str, Any]:
        """Trigger the memory pipeline and poll until a terminal status is reached.

        Tolerates up to `MAX_CONSECUTIVE_POLL_ERRORS` transient poll failures
        in a row before propagating the underlying error.
        """
        run_id = self.trigger_memory_pipeline(max_files=max_files, batch_size=batch_size)
        logger.info(
            "Pam memory pipeline triggered (run_id=%s); polling every %ss",
            run_id,
            self.MEMORY_POLL_INTERVAL,
        )

        start = time.time()
        consecutive_errors = 0
        while True:
            time.sleep(self.MEMORY_POLL_INTERVAL)

            try:
                status_resp = self.poll_memory_status()
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                elapsed_min = (time.time() - start) / 60
                logger.warning(
                    "Pam memory pipeline poll error [%.1fm] (%d/%d): %r",
                    elapsed_min,
                    consecutive_errors,
                    self.MAX_CONSECUTIVE_POLL_ERRORS,
                    e,
                )
                if consecutive_errors >= self.MAX_CONSECUTIVE_POLL_ERRORS:
                    raise
                continue

            run_info = status_resp.get("run", status_resp)
            last_status = run_info.get("run_status", run_info.get("status", "unknown"))
            elapsed_min = (time.time() - start) / 60
            logger.info("Pam memory pipeline [%.1fm] status=%s", elapsed_min, last_status)

            if last_status in self.TERMINAL_STATUSES:
                if last_status != "completed":
                    error_msg = run_info.get("run_error_message", "no details")
                    raise RuntimeError(f"Pam memory pipeline {last_status}: {error_msg}")
                return status_resp

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
