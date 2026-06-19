"""Vertex AI auth for Claude Code.

Builds the environment Claude Code needs to talk to Claude on GCP Vertex AI from
the benchmark's own secrets (`VERTEX_PROJECT_ID`, `VERTEX_REGION`,
`GOOGLE_APPLICATION_CREDENTIALS`). The credentials value may be:
  - a local file path;
  - a `gs://bucket/key` URI (downloaded to a local temp file); or
  - an `sm://projects/<P>/secrets/<S>[/versions/<V>]` reference to a Secret
    Manager secret whose payload is the service-account key JSON (as text).
The `gs://`/`sm://` forms are resolved once to a local temp file (cached for the
process) since Claude Code / the GCP SDK expect a local path.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

from env import require

logger = logging.getLogger(__name__)

# Resolved credentials (gs:// download / sm:// fetch), cached per source.
_resolved_credentials: dict[str, str] = {}

_SM_RESOURCE_RE = re.compile(
    r"^projects/(?P<project>[^/]+)/secrets/(?P<secret>[^/]+)(?:/versions/(?P<version>[^/]+))?$"
)


def _write_creds_tempfile(payload: str) -> str:
    fd, local_path = tempfile.mkstemp(prefix="pam_creds_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(payload)
    return local_path


def _fetch_secret_manager(resource: str) -> str:
    """Read the SA-key JSON from a Secret Manager resource and write it locally.

    `resource` is the part after `sm://`, e.g.
    `projects/<P>/secrets/<S>` or `.../versions/<V>` (defaults to `latest`).
    Uses Application Default Credentials (ambient gcloud / metadata server);
    prefers the Secret Manager SDK, falls back to the gcloud CLI.
    """
    if resource in _resolved_credentials:
        return _resolved_credentials[resource]

    m = _SM_RESOURCE_RE.match(resource)
    if not m:
        raise ValueError(
            f"invalid sm:// secret resource: {resource!r} "
            "(expected projects/<P>/secrets/<S>[/versions/<V>])"
        )
    project, secret_id, version = m["project"], m["secret"], m["version"] or "latest"
    name = f"projects/{project}/secrets/{secret_id}/versions/{version}"

    try:
        from google.cloud import secretmanager  # type: ignore

        client = secretmanager.SecretManagerServiceClient()
        payload = client.access_secret_version(name=name).payload.data.decode("utf-8")
    except ImportError:
        out = subprocess.run(
            [
                "gcloud",
                "secrets",
                "versions",
                "access",
                version,
                f"--secret={secret_id}",
                f"--project={project}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = out.stdout

    local_path = _write_creds_tempfile(payload)
    _resolved_credentials[resource] = local_path
    logger.info("Loaded Vertex credentials from Secret Manager %s -> %s", name, local_path)
    return local_path


def _download_gcs(gs_uri: str) -> str:
    """Download a `gs://bucket/key` object to a local temp file; return its path."""
    if gs_uri in _resolved_credentials:
        return _resolved_credentials[gs_uri]

    suffix = Path(gs_uri).suffix or ".json"
    fd, local_path = tempfile.mkstemp(prefix="pam_creds_", suffix=suffix)
    os.close(fd)

    try:
        # Prefer the GCS SDK if available; fall back to the gcloud CLI.
        from google.cloud import storage  # type: ignore

        without_scheme = gs_uri[len("gs://") :]
        bucket_name, _, blob_name = without_scheme.partition("/")
        storage.Client().bucket(bucket_name).blob(blob_name).download_to_filename(local_path)
    except ImportError:
        subprocess.run(["gcloud", "storage", "cp", gs_uri, local_path], check=True)

    _resolved_credentials[gs_uri] = local_path
    logger.info("Resolved Vertex credentials %s -> %s", gs_uri, local_path)
    return local_path


def resolve_credentials(path: str) -> str:
    """Return an ABSOLUTE local path to the credentials file.

    `gs://` URIs are downloaded; `sm://projects/.../secrets/...` references are
    fetched from Secret Manager; local (possibly relative) paths are resolved to
    absolute. Absolute is required because the harness runs `claude` with its
    cwd set to the per-sample memory dir, so a relative path would resolve
    against the wrong directory.
    """
    if path.startswith("gs://"):
        return _download_gcs(path)
    if path.startswith("sm://"):
        return _fetch_secret_manager(path[len("sm://") :])
    local = Path(path).expanduser().resolve()
    if not local.exists():
        raise FileNotFoundError(
            f"GOOGLE_APPLICATION_CREDENTIALS not found: {path} (resolved to {local})"
        )
    return str(local)


def vertex_env() -> dict[str, str]:
    """The env Claude Code needs for Vertex AI, derived from benchmark secrets.

    Credentials come from `GOOGLE_APPLICATION_CREDENTIALS` — a local path, a
    `gs://` URI, or an `sm://` Secret Manager reference. The base model is NOT
    set here — it is passed per-invocation via `--model` (`--harness-model`).
    """
    creds = resolve_credentials(require("GOOGLE_APPLICATION_CREDENTIALS"))
    return {
        "CLAUDE_CODE_USE_VERTEX": "1",
        "ANTHROPIC_VERTEX_PROJECT_ID": require("VERTEX_PROJECT_ID"),
        "CLOUD_ML_REGION": require("VERTEX_REGION"),
        "GOOGLE_APPLICATION_CREDENTIALS": creds,
    }
