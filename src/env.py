"""Load environment variables from secrets.env when present.

In production (Cloud Run Jobs) we rely on Secret Manager injecting env vars,
so this is effectively a no-op there.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

SECRETS_FILENAMES = ("secrets.env", ".env")


def load_secrets(*, repo_root: Path | None = None) -> None:
    root = repo_root or _find_repo_root()
    for name in SECRETS_FILENAMES:
        path = root / name
        if path.exists():
            load_dotenv(path, override=False)
            logger.debug("Loaded env from %s", path)
            return
    logger.debug("No secrets file found; relying on already-set env vars")


def _find_repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return here


def require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"required env var not set: {name}")
    return val
