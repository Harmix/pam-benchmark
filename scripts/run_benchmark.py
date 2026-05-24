"""Benchmark run entrypoint.

Adds `src/` to `sys.path` for the no-wrapper-package layout, then delegates
to `cli.app`. All real work is in `src/cli.py` and `src/runner.py`.

Usage:
    uv run python scripts/run_benchmark.py --dataset locomo --baseline gpt-4-turbo --exp-name <name>
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cli import app  # noqa: E402

if __name__ == "__main__":
    app()
