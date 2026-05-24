"""Small file IO helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def read_json(path: Path | str) -> Any:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path | str, data: Any, *, indent: int = 2) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=indent, default=str)


def sha256(path: Path | str, chunk: int = 1 << 16) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()
