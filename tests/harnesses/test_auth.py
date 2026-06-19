"""Credential resolution by scheme (local / gs:// / sm://)."""

from __future__ import annotations

import pytest

from harnesses.claude_code import auth


def test_local_path_resolved_to_absolute(tmp_path):
    p = tmp_path / "creds.json"
    p.write_text("{}")
    out = auth.resolve_credentials(str(p))
    assert out == str(p.resolve())


def test_missing_local_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        auth.resolve_credentials(str(tmp_path / "nope.json"))


def test_gs_scheme_routes_to_download(monkeypatch):
    monkeypatch.setattr(auth, "_download_gcs", lambda uri: f"/tmp/dl::{uri}")
    assert auth.resolve_credentials("gs://b/k.json") == "/tmp/dl::gs://b/k.json"


def test_sm_scheme_routes_to_secret_manager(monkeypatch):
    seen = {}

    def fake(resource):
        seen["resource"] = resource
        return "/tmp/sm-creds.json"

    monkeypatch.setattr(auth, "_fetch_secret_manager", fake)
    out = auth.resolve_credentials("sm://projects/P/secrets/S")
    assert out == "/tmp/sm-creds.json"
    assert seen["resource"] == "projects/P/secrets/S"  # sm:// stripped


def test_sm_resource_regex_parses_versioned_and_default():
    m = auth._SM_RESOURCE_RE.match("projects/p/secrets/s/versions/7")
    assert (m["project"], m["secret"], m["version"]) == ("p", "s", "7")
    m = auth._SM_RESOURCE_RE.match("projects/p/secrets/s")
    assert (m["project"], m["secret"], m["version"]) == ("p", "s", None)


def test_invalid_sm_resource_raises(monkeypatch):
    # Force the SDK-import branch to be skipped by giving a malformed resource;
    # the regex check happens before any network/CLI call.
    auth._resolved_credentials.clear()
    with pytest.raises(ValueError, match="invalid sm:// secret resource"):
        auth._fetch_secret_manager("not-a-valid-resource")


def test_no_hardcoded_secret_in_module():
    src = __import__("inspect").getsource(auth)
    assert "230114846813" not in src
    assert "pam-benchmark-agent-credentials" not in src
