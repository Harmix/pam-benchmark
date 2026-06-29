# MemTrack (placeholder)

Slot reserved for the **MemTrack** benchmark — *MemTrack: Evaluating Long-Term Memory and State Tracking in Multi-Platform Dynamic Agent Environments* (Deshpande et al., **NeurIPS 2025 SEA Workshop**). **Not yet integrated** into the runner.

- **Paper:** https://arxiv.org/abs/2510.01353

MemTrack evaluates how well agents acquire, select, and reconcile long-term memory while tracking state across realistic, noisy multi-platform workflows (**Slack + Linear + Git**) with asynchronous events, codebase/file-system context, and conflicting cross-platform information. That shape is close to what [Pam](https://manager.harmix.ai) sees in production, which is why it's high on our roadmap.

Existing assets under `data/`:
- `test_configs/` — YAML files defining benchmark scenarios
- `test_event_histories/` — JSON event histories
- `registry.json` — legacy registry (not used by the new runner)

When integrated:
- `loader.py` — implements `DatasetLoader` from `datasets.base`
- `schemas.py` — pydantic models for the sample shape
- `pipeline.py` (under `src/tasks/memtrack/`) — task orchestration

See `docs/benchmark_rewrite_plan.md` §14 for milestone planning.
