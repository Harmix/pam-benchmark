"""PamClient.wait_for_memory polling loop — `completed` / `failed` / `pending`.

`time.sleep` is monkeypatched away so the test doesn't actually wait 30s
between iterations.
"""

from __future__ import annotations

from typing import Any

import pytest
import requests

from baselines.pam import client as pam_client_mod
from baselines.pam.client import PamAuthError, PamClient


class _FakeResp:
    """Minimal stand-in for `requests.Response` for status-code tests."""

    def __init__(self, status_code: int, body: bytes | str = b""):
        self.status_code = status_code
        self.text = body if isinstance(body, str) else body.decode("utf-8", errors="replace")
        self.ok = 200 <= status_code < 300
        self._body = body if isinstance(body, bytes) else body.encode()

    def json(self) -> Any:
        import json as _json

        return _json.loads(self._body or b"{}")

    def raise_for_status(self) -> None:
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch):
    """Skip the real `time.sleep` so polling loops finish instantly."""
    monkeypatch.setattr(pam_client_mod.time, "sleep", lambda _s: None)


def _client_with_user(uid: int = 42) -> PamClient:
    c = PamClient("http://stub")
    c.user_id = uid
    c.admin_token = "admin-token"
    return c


def test_wait_for_memory_completes_after_pending_iterations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two `pending` polls followed by `completed` — loop exits cleanly."""
    c = _client_with_user()
    statuses = iter(
        [
            {"status": "pending"},
            {"status": "pending"},
            {"status": "completed"},
        ]
    )
    seen_run_ids: list[str] = []

    def fake_status(run_id: str, user_id: int | None = None) -> dict[str, Any]:
        seen_run_ids.append(run_id)
        return next(statuses)

    monkeypatch.setattr(c, "get_memory_pipeline_status", fake_status)
    c.wait_for_memory(["run-A"])
    assert seen_run_ids == ["run-A", "run-A", "run-A"]


def test_wait_for_memory_raises_on_failed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _client_with_user()
    failure = {
        "status": "failed",
        "error_stage": "extract",
        "error_message": "boom",
    }

    monkeypatch.setattr(c, "get_memory_pipeline_status", lambda *a, **kw: failure)

    with pytest.raises(RuntimeError, match=r"failed.*stage=extract.*boom"):
        c.wait_for_memory(["run-bad"])


def test_wait_for_memory_unknown_status_keeps_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unrecognized run_status maps to `pending` server-side, so we keep
    polling instead of treating it as terminal."""
    c = _client_with_user()
    statuses = iter([{"status": "weird"}, {"status": "completed"}])

    monkeypatch.setattr(c, "get_memory_pipeline_status", lambda *a, **kw: next(statuses))
    c.wait_for_memory(["run-weird"])  # no raise


def test_wait_for_memory_tolerates_transient_poll_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Up to MAX_CONSECUTIVE_POLL_ERRORS - 1 transient errors are absorbed
    and the loop continues once a clean response arrives."""
    c = _client_with_user()
    attempts = {"n": 0}

    def fake_status(run_id: str, user_id: int | None = None) -> dict[str, Any]:
        attempts["n"] += 1
        if attempts["n"] <= PamClient.MAX_CONSECUTIVE_POLL_ERRORS - 1:
            raise RuntimeError("transient")
        return {"status": "completed"}

    monkeypatch.setattr(c, "get_memory_pipeline_status", fake_status)
    c.wait_for_memory(["run-flaky"])
    assert attempts["n"] == PamClient.MAX_CONSECUTIVE_POLL_ERRORS


def test_wait_for_memory_propagates_after_too_many_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MAX_CONSECUTIVE_POLL_ERRORS in a row → raise the underlying exception."""
    c = _client_with_user()

    def always_fails(run_id: str, user_id: int | None = None):
        raise RuntimeError("repeated network failure")

    monkeypatch.setattr(c, "get_memory_pipeline_status", always_fails)

    with pytest.raises(RuntimeError, match="repeated network failure"):
        c.wait_for_memory(["run-doomed"])


def test_wait_for_memory_requires_user_id() -> None:
    c = PamClient("http://stub")  # no user_id, no login
    with pytest.raises(ValueError, match="wait_for_memory requires user_id"):
        c.wait_for_memory(["run-x"])


# --- Auth-error handling (401/403 → PamAuthError, fatal) ------------------


def test_wait_for_memory_does_not_absorb_pam_auth_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PamAuthError from the status endpoint must propagate on the first
    occurrence — not be counted toward MAX_CONSECUTIVE_POLL_ERRORS. A misconfigured
    token won't fix itself by retrying, and we don't want a stuck-pipeline
    appearance."""
    c = _client_with_user()
    calls = {"n": 0}

    def fake_status(run_id: str, user_id: int | None = None) -> dict[str, Any]:
        calls["n"] += 1
        raise PamAuthError(403, "http://stub/.../poll", "token does not belong to user_id")

    monkeypatch.setattr(c, "get_memory_pipeline_status", fake_status)

    with pytest.raises(PamAuthError, match="HTTP 403"):
        c.wait_for_memory(["run-x"])
    assert calls["n"] == 1  # no retry — first iteration's failure propagates


def test_get_memory_pipeline_status_raises_on_403_without_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 403 means the bearer token doesn't authorize this user_id — refreshing
    the same token won't help, so we raise immediately."""
    c = _client_with_user()
    refresh_calls = {"n": 0}
    monkeypatch.setattr(
        c, "refresh_token", lambda: refresh_calls.__setitem__("n", refresh_calls["n"] + 1)
    )
    monkeypatch.setattr(
        c.session, "get", lambda *_a, **_kw: _FakeResp(403, b"forbidden - wrong user")
    )

    with pytest.raises(PamAuthError) as ei:
        c.get_memory_pipeline_status("run-x")
    assert ei.value.status_code == 403
    assert refresh_calls["n"] == 0


def test_get_memory_pipeline_status_refreshes_then_raises_on_persistent_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First 401 → refresh once and retry. If the second attempt is also 401,
    raise PamAuthError (the misconfiguration is fatal)."""
    c = _client_with_user()
    refresh_calls = {"n": 0}
    monkeypatch.setattr(
        c, "refresh_token", lambda: refresh_calls.__setitem__("n", refresh_calls["n"] + 1)
    )
    monkeypatch.setattr(
        c.session, "get", lambda *_a, **_kw: _FakeResp(401, b"missing/expired token")
    )

    with pytest.raises(PamAuthError) as ei:
        c.get_memory_pipeline_status("run-x")
    assert ei.value.status_code == 401
    assert refresh_calls["n"] == 1


def test_process_generic_files_raises_on_403_without_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _client_with_user()
    refresh_calls = {"n": 0}
    monkeypatch.setattr(
        c, "refresh_token", lambda: refresh_calls.__setitem__("n", refresh_calls["n"] + 1)
    )
    monkeypatch.setattr(
        c.session, "post", lambda *_a, **_kw: _FakeResp(403, b"forbidden - wrong user")
    )

    with pytest.raises(PamAuthError) as ei:
        c.process_generic_files([("x.json", b"{}")])
    assert ei.value.status_code == 403
    assert refresh_calls["n"] == 0


def test_process_generic_files_refreshes_then_raises_on_persistent_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _client_with_user()
    refresh_calls = {"n": 0}
    monkeypatch.setattr(
        c, "refresh_token", lambda: refresh_calls.__setitem__("n", refresh_calls["n"] + 1)
    )
    monkeypatch.setattr(
        c.session, "post", lambda *_a, **_kw: _FakeResp(401, b"missing/expired token")
    )

    with pytest.raises(PamAuthError) as ei:
        c.process_generic_files([("x.json", b"{}")])
    assert ei.value.status_code == 401
    assert refresh_calls["n"] == 1


def test_process_generic_files_returns_run_id_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity: when the per-user bearer is valid, the endpoint returns 200 + a
    run_id, the auth helper is a no-op, and the run_id flows through."""
    c = _client_with_user()
    monkeypatch.setattr(
        c.session,
        "post",
        lambda *_a, **_kw: _FakeResp(200, b'{"run_id": "run-ok-0"}'),
    )

    run_ids = c.process_generic_files([("x.json", b"{}")])
    assert run_ids == ["run-ok-0"]


# --- issue_user_tokens (debug-mode per-user token mint) -------------------


def test_issue_user_tokens_sends_api_key_and_admin_bearer_and_sets_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mints a per-user token via the admin endpoint and adopts it as the
    current access token (so chat runs as that user). The request must carry
    BOTH the api-key header (route gate) AND the admin bearer (API edge gate)."""
    c = PamClient("http://stub", api_key="harmix-secret")
    c.admin_token = "admin-jwt"  # set by login() in a real run
    seen: dict[str, Any] = {}

    def fake_post(url, headers=None, timeout=None, **_kw):
        seen["url"] = url
        seen["headers"] = headers
        return _FakeResp(200, b'{"access_token": "tok-777", "refresh_token": "ref-777"}')

    monkeypatch.setattr(c.session, "post", fake_post)

    token = c.issue_user_tokens(777)
    assert token == "tok-777"
    assert c.access_token == "tok-777"
    assert c.user_id == 777
    assert seen["url"].endswith("/admin/users/777/tokens")
    # Both headers present: api-key (route) + admin bearer (edge).
    assert seen["headers"]["api-key"] == "harmix-secret"
    assert seen["headers"]["Authorization"] == "Bearer admin-jwt"


def test_issue_user_tokens_refreshes_admin_bearer_on_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A first 401 (expired admin bearer at the edge) → refresh once and retry."""
    c = PamClient("http://stub", api_key="harmix-secret")
    c.admin_token = "stale-jwt"
    c._admin_email = "admin@stub"
    c._admin_password = "pw"

    def fake_refresh() -> None:
        c.admin_token = "fresh-jwt"

    monkeypatch.setattr(c, "refresh_token", fake_refresh)

    seen_auth: list[str | None] = []
    statuses = iter([401, 200])

    def fake_post(url, headers=None, timeout=None, **_kw):
        seen_auth.append(headers.get("Authorization"))
        code = next(statuses)
        body = b'{"access_token": "tok-1"}' if code == 200 else b"unauth"
        return _FakeResp(code, body)

    monkeypatch.setattr(c.session, "post", fake_post)

    assert c.issue_user_tokens(5) == "tok-1"
    # First attempt used the stale bearer; retry used the refreshed one.
    assert seen_auth == ["Bearer stale-jwt", "Bearer fresh-jwt"]


def test_issue_user_tokens_requires_api_key() -> None:
    c = PamClient("http://stub")  # no api_key configured
    with pytest.raises(RuntimeError, match="requires an api_key"):
        c.issue_user_tokens(777)


def test_issue_user_tokens_raises_pam_auth_error_on_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bad/absent api-key surfaces as PamAuthError, not a silent failure."""
    c = PamClient("http://stub", api_key="wrong-key")
    monkeypatch.setattr(c.session, "post", lambda *_a, **_kw: _FakeResp(403, b"bad key"))
    with pytest.raises(PamAuthError) as ei:
        c.issue_user_tokens(777)
    assert ei.value.status_code == 403


def test_process_generic_files_retry_resends_full_body_not_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a 401-then-retry must transmit the real file bytes again.

    `requests` reads each upload stream to EOF while encoding the multipart
    body, so reusing one BytesIO across the retry would send an empty file —
    which the server stages as a zero-byte `*_conversation.txt` in the zip.
    Each attempt must build a fresh stream. We simulate `requests` by draining
    every file stream on each POST and recording what was read.
    """
    c = _client_with_user()
    monkeypatch.setattr(c, "refresh_token", lambda: None)

    content = b'{"sample_id": "conv-26", "session_1": [{"text": "hi"}]}'
    bodies_seen: list[bytes] = []
    statuses = iter([401, 200])

    def fake_post(url, headers=None, files=None, timeout=None, **_kw):
        # Mimic requests: read each stream to EOF (consuming it).
        drained = b"".join(stream.read() for _field, (_name, stream, _ctype) in files)
        bodies_seen.append(drained)
        code = next(statuses)
        body = b'{"run_id": "run-ok-0"}' if code == 200 else b"unauthorized"
        return _FakeResp(code, body)

    monkeypatch.setattr(c.session, "post", fake_post)

    run_ids = c.process_generic_files([("conv-26_conversation.txt", content)])

    assert run_ids == ["run-ok-0"]
    # Two attempts were made, and BOTH carried the full content — the retry
    # was not an empty body.
    assert len(bodies_seen) == 2
    assert bodies_seen[0] == content
    assert bodies_seen[1] == content
