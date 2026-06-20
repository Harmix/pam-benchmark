"""MCP-memory-on-harness benchmark entrypoint.

Adds `src/` to `sys.path` for the no-wrapper-package layout, then delegates to
`mcp_cli.app`. Evaluates an MCP memory baseline (e.g. memory_md_mcp) running on
an agentic harness (e.g. claude-code) — the counterpart to
`scripts/run_benchmark.py` for the harness experiment.

Usage:
    uv run python scripts/run_mcp_benchmark.py \
        --dataset locomo --harness claude-code --baseline memory_md_mcp \
        --harness-model <vertex-model-id> --exp-name mcp_locomo_md_v1 \
        --mcp-batch-size 10 --max-questions 20
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mcp_cli import app  # noqa: E402

if __name__ == "__main__":
    app()
