# Active Tasks

## Milestone

**M2 (next):** port Pam ([manager.harmix.ai](https://manager.harmix.ai)) off Harbor onto the new harness as the system under test, then run ≥3 seeds and report results with bootstrap CIs / paired bootstrap significance.

M1 is complete: the rewritten harness ran `gpt-4-turbo` on LoCoMo end-to-end, results landed in MongoDB, and the repo is tagged `m1`. Detailed plan: `docs/benchmark_rewrite_plan.md` §14 (M2 line item).

## In Progress

**MCP-memory-on-harness experiment (new track).** Evaluate MCP memory baselines running on an agentic harness, to compare Pam against the recognizable filesystem-memory baseline. First milestone: **`--harness claude-code` + `--baseline memory_md_mcp`** (Obsidian-Markdown filesystem memory) on LoCoMo, via `scripts/run_mcp_benchmark.py`. Plan: `docs/mcp_harness_benchmark_plan.md` (decisions locked). System card: `.memory-bank/baselines/system-cards.md` → "Claude Code + `memory_md_mcp`". Code landed: `src/harnesses/` (Harness abstraction, Claude Code on Vertex), `src/baselines/mcp/` (McpMemoryBackend + composing baseline), shared `src/batch_protocol.py`; unit-tested with a fake harness (no Claude Code / network). **Remaining before a real run:** confirm the Claude Code CLI flags + Vertex region var against the installed `claude` (M0 spike), set `VERTEX_*` / `GOOGLE_APPLICATION_CREDENTIALS` in `secrets.env`, then a `--max-questions` debug run before a full LoCoMo run.

## Blocked / Needs Decision

_None._
