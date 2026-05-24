"""Logger configuration — rich for humans, JSON for Cloud Logging.

Named `log_setup.py` (not `logging.py`) to avoid shadowing the stdlib `logging`
module when `src/` is on PYTHONPATH.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from rich.logging import RichHandler


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for k, v in record.__dict__.items():
            if k.startswith("_"):
                continue
            if k in {
                "args", "msg", "levelname", "name", "created", "exc_info", "exc_text",
                "filename", "funcName", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName", "relativeCreated",
                "stack_info", "thread", "threadName", "taskName",
            }:
                continue
            payload[k] = v
        return json.dumps(payload, default=str)


def configure(log_format: str = "rich", level: int = logging.INFO) -> None:
    """Initialize root logging once."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(level)

    if log_format == "json":
        handler: logging.Handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(_JsonFormatter())
    else:
        handler = RichHandler(rich_tracebacks=True, show_path=False)
    root.addHandler(handler)

    # Silence the loudest third parties.
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
