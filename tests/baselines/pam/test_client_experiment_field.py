"""PamClient maps `--pam-exp-config` onto the memory pipeline's own field name.

The benchmark-internal name is `pam_exp_config`, but the wire field the memory
pipeline reads is `experiment` (→ `--experiment` in the workflow). These tests
lock that mapping and the "omit when unset" default.
"""

from __future__ import annotations

from typing import Any

import pytest

from baselines.pam.client import PamClient


class _OK:
    status_code = 200
    ok = True
    text = ""

    def __init__(self, data: dict[str, Any]):
        self._d = data

    def json(self) -> dict[str, Any]:
        return self._d

    def raise_for_status(self) -> None:
        return None


def _client(uid: int = 7) -> PamClient:
    c = PamClient("http://stub")
    c.user_id = uid
    c.access_token = "tok"
    return c


def _capture(monkeypatch: pytest.MonkeyPatch, c: PamClient) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kw: Any) -> _OK:
        calls.append(kw)
        return _OK({"run_id": "r1"})

    monkeypatch.setattr(c.session, "post", fake_post)
    return calls


def test_process_snapshot_sends_experiment_wire_field(monkeypatch):
    c = _client()
    calls = _capture(monkeypatch, c)
    c.process_snapshot("gs://x.zip", ["gmail"], pam_exp_config="introspective_v2")
    body = calls[-1]["json"]
    assert body["experiment"] == "introspective_v2"  # wire field is `experiment`
    assert "pam_exp_config" not in body


def test_process_snapshot_omits_field_when_unset(monkeypatch):
    c = _client()
    calls = _capture(monkeypatch, c)
    c.process_snapshot("gs://x.zip", ["gmail"])
    assert "experiment" not in calls[-1]["json"]


def test_process_generic_files_sends_experiment_form_field(monkeypatch):
    c = _client()
    calls = _capture(monkeypatch, c)
    c.process_generic_files([("f.json", b"{}")], pam_exp_config="flash_reasoning")
    assert calls[-1]["data"] == {"experiment": "flash_reasoning"}


def test_process_generic_files_omits_form_when_unset(monkeypatch):
    c = _client()
    calls = _capture(monkeypatch, c)
    c.process_generic_files([("f.json", b"{}")])
    assert calls[-1]["data"] is None
