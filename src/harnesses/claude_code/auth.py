"""Vertex AI auth for Claude Code.

Builds the environment Claude Code needs to talk to Claude on GCP Vertex AI from
the benchmark's own secrets (`VERTEX_PROJECT_ID`, `VERTEX_REGION`,
`GOOGLE_APPLICATION_CREDENTIALS`). The credentials path may be a local file or a
`gs://` URI; a `gs://` URI is downloaded once to a local temp file (cached for
the process) since Claude Code / the GCP SDK expect a local path.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from env import require

logger = logging.getLogger(__name__)

# Resolved (gs:// → local) credentials, cached per URI for the process.
_resolved_credentials: dict[str, str] = {}


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
    """Return an ABSOLUTE local path to the credentials file. `gs://` URIs are
    downloaded; local (possibly relative) paths are resolved to absolute.

    Absolute is required because the harness runs `claude` with its cwd set to
    the per-sample memory dir, so a relative path would resolve against the
    wrong directory.
    """
    if path.startswith("gs://"):
        return _download_gcs(path)
    local = Path(path).expanduser().resolve()
    if not local.exists():
        raise FileNotFoundError(
            f"GOOGLE_APPLICATION_CREDENTIALS not found: {path} (resolved to {local})"
        )
    return str(local)


def vertex_env() -> dict[str, str]:
    """The env Claude Code needs for Vertex AI, derived from benchmark secrets.

    The base model is NOT set here — it is passed per-invocation via `--model`
    (the `--harness-model` CLI flag).
    """
    creds = resolve_credentials(require("GOOGLE_APPLICATION_CREDENTIALS"))
    return {
        "CLAUDE_CODE_USE_VERTEX": "1",
        "ANTHROPIC_VERTEX_PROJECT_ID": require("VERTEX_PROJECT_ID"),
        "CLOUD_ML_REGION": require("VERTEX_REGION"),
        "GOOGLE_APPLICATION_CREDENTIALS": creds,
    }
