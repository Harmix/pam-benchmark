"""Credential resolution by scheme (local / gs:// / sm://)."""

from __future__ import annotations

from pathlib import Path

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


def test_vertex_env_reads_vertex_credentials_and_exports_gac(monkeypatch):
    # Input var is VERTEX_CREDENTIALS; resolved local path is exported as
    # GOOGLE_APPLICATION_CREDENTIALS for the claude subprocess.
    monkeypatch.setenv("VERTEX_CREDENTIALS", "sm://projects/p/secrets/s")
    monkeypatch.setenv("VERTEX_PROJECT_ID", "proj-123")
    monkeypatch.setenv("VERTEX_REGION", "us-east5")
    monkeypatch.setattr(auth, "_fetch_secret_manager", lambda res: "/tmp/resolved.json")

    env = auth.vertex_env()
    assert env["GOOGLE_APPLICATION_CREDENTIALS"] == "/tmp/resolved.json"
    assert env["ANTHROPIC_VERTEX_PROJECT_ID"] == "proj-123"
    assert env["CLOUD_ML_REGION"] == "us-east5"
    assert env["CLAUDE_CODE_USE_VERTEX"] == "1"


def test_fetch_secret_manager_uses_sdk(monkeypatch):
    """The fetch works via the SDK without touching GOOGLE_APPLICATION_CREDENTIALS
    (our input var is VERTEX_CREDENTIALS, so ADC is never confused by it)."""
    import sys
    import types

    auth._resolved_credentials.clear()
    captured: dict[str, object] = {}

    class _FakeClient:
        def access_secret_version(self, *, name):
            captured["name"] = name
            return types.SimpleNamespace(payload=types.SimpleNamespace(data=b'{"k": "v"}'))

    sm_mod = types.ModuleType("google.cloud.secretmanager")
    sm_mod.SecretManagerServiceClient = _FakeClient
    cloud_mod = types.ModuleType("google.cloud")
    cloud_mod.secretmanager = sm_mod
    google_mod = types.ModuleType("google")
    google_mod.cloud = cloud_mod
    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud_mod)
    monkeypatch.setitem(sys.modules, "google.cloud.secretmanager", sm_mod)

    path = auth._fetch_secret_manager("projects/p/secrets/s")
    assert captured["name"] == "projects/p/secrets/s/versions/latest"
    assert Path(path).read_text() == '{"k": "v"}'


def test_no_legacy_gac_input_in_module():
    # We must not read GOOGLE_APPLICATION_CREDENTIALS as our INPUT var anymore;
    # it should only appear as the OUTPUT key for the subprocess env.
    src = __import__("inspect").getsource(auth)
    assert 'require("GOOGLE_APPLICATION_CREDENTIALS")' not in src
    assert 'os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS"' not in src
