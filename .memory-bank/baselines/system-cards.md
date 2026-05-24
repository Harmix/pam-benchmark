# System Cards

One card per baseline. M1 ships exactly one. M2+ adds PAM (our solution), then competitors.

---

## Baseline: gpt-4-turbo (M1)

- **Identity:** OpenAI `gpt-4-turbo` via LiteLLM. Specific model snapshot determined by OpenAI's `gpt-4-turbo` alias at run time (recorded in the Mongo doc per run; pin via `--baseline-kwargs '{"model": "gpt-4-turbo-2024-04-09"}'` for strict reproducibility).
- **Type:** competitor / external baseline (we don't control the weights).
- **Architecture & params:** not publicly disclosed.
- **Training data:** OpenAI cutoff per model card; unknown whether LoCoMo samples are present.
- **Intended use:** general-purpose chat completion; we use single-call QA.
- **Out-of-scope use:** per OpenAI usage policies (https://openai.com/policies/usage-policies).
- **Configuration in this benchmark:** `temperature=0.0`, `max_tokens=1024` (defaults). Prompt construction lives in `src/tasks/locomo/prompts.py`. Single-call per question; no batching in M1.
- **Cost & latency profile:** measured per run; aggregated in `total_cost_usd`, `p50/p95_latency_ms` on each Mongo doc and the report.
- **License / ToS:** standard OpenAI API ToS. Published comparisons: verify against OpenAI Brand Guidelines + Usage Policies before any external release (see [[licensing-and-data-handling]]).
- **Metrics on this benchmark:** queried from MongoDB (`locomo_results` collection, filter `exp_name`); rendered via `scripts/generate_report.py --exp-name <name>`. Not duplicated here.
- **Caveats:** model snapshot drift over time — record the exact model id used in each run (`baseline_kwargs.model` on the Mongo doc).
- **Date of last evaluation:** TBD (first M1 acceptance run).

---

_Placeholder cards for M2+ baselines (PAM, Honcho, Supermemory, mem0, Zep, Claude Code + Memory.md, Claude Code + Obsidian, OpenClaw + .md) will be added when each is integrated._
