# LongMemEval (placeholder)

Slot reserved for the LongMemEval dataset — long-conversation memory eval added in M7 of [Harmix](https://manager.harmix.ai)'s Pam benchmark. Not implemented in M1.

When added:
- `loader.py` — implements `DatasetLoader` from `datasets.base`
- `schemas.py` — pydantic models for the sample shape
- `data/` — gitignored; populated by `scripts/download_data.py --dataset longmemeval`

See `docs/benchmark_rewrite_plan.md` §14 for milestone planning.
