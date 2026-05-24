# MEMTRACK (placeholder)

Slot reserved for the MEMTRACK dataset — Harmix's internal synthetic dataset of Linear + Slack event histories. **Not active in M1** — kept for the future port off the legacy Harbor flow.

MEMTRACK is the closest public-style benchmark to what [Pam](https://manager.harmix.ai) sees in production: multi-tool coordination data with cross-system references. It's the dataset Harmix prospects will most likely ask about when evaluating Pam's memory layer.

Existing assets under `data/`:
- `test_configs/` — YAML files defining benchmark scenarios (Linear + Slack)
- `test_event_histories/` — JSON event histories
- `registry.json` — legacy Harbor registry (not used by the new runner)

When integrated:
- `loader.py` — implements `DatasetLoader` from `datasets.base`
- `schemas.py` — pydantic models for the sample shape
- `pipeline.py` (under `src/tasks/memtrack/`) — task orchestration

See `docs/benchmark_rewrite_plan.md` §14 for milestone planning.
