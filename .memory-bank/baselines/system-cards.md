# System Cards

One card per baseline. M1 ships exactly one (`gpt-4-turbo`). M2 adds **Pam** ([manager.harmix.ai](https://manager.harmix.ai)) — Harmix's Proactive AI Manager — as the system under test the rest of the cards are compared against. M4–M5 add the dedicated memory competitors (Honcho, Supermemory, mem0, Zep, Claude Code + Memory.md, Claude Code + Obsidian, OpenClaw + .md).

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
- **Date of last evaluation:** 2026-05 (M1 acceptance run completed; image digest recorded in the repo tag `m1`).

---

## Baseline: Pam (Harmix) — M2 target

- **Identity:** Pam (Proactive AI Manager), Harmix's enterprise AI business assistant. Product page: <https://manager.harmix.ai>.
- **Type:** the system under test — the reason this benchmark exists.
- **What it is:** Pam learns continuously from organizational data (documents, ERP/CRM systems, Linear, Slack, retrospectives) to anticipate problems, automate workflows, and resolve conflicts across disparate tools. The memory layer being benchmarked here is the foundation those higher-level capabilities sit on top of.
- **Configuration in this benchmark:** documented at integration time in M2; exact memory backbone, model, and retrieval config will be recorded in `baseline_kwargs` on every Mongo doc for reproducibility.
- **License / ToS:** Harmix-internal. Published comparisons follow [[licensing-and-data-handling]].
- **Date of last evaluation:** N/A until M2.

---

_Placeholder cards for the M4–M5 memory competitors (Honcho, Supermemory, mem0, Zep, Claude Code + Memory.md, Claude Code + Obsidian, OpenClaw + .md) will be added when each is integrated._
