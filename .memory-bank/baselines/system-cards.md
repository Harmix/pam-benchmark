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

## Baseline: Pam (Harmix) — M2

- **Identity:** Pam (Proactive AI Manager), Harmix's enterprise AI business assistant. Product page: <https://manager.harmix.ai>.
- **Type:** the system under test — the reason this benchmark exists. `track = "memory_product"`.
- **What it is:** Pam learns continuously from organizational data (documents, ERP/CRM systems, Linear, Slack, retrospectives) to anticipate problems, automate workflows, and resolve conflicts across disparate tools. The memory layer being benchmarked here is the foundation those higher-level capabilities sit on top of.
- **Integration:** `src/baselines/pam/`. Per LoCoMo sample, the harness creates a fresh Pam user, uploads the sample's conversation as `<sample_id>_conversation.json` (preserving original session order from `locomo10.json`), triggers Pam's `benchmark_memory` pipeline (polled every 30s until terminal status), then answers the sample's questions in batches via SSE. The user is deleted after the sample completes.
- **Batched-question protocol:** one SSE call per chunk of `--pam-batch-size` questions (default 10). The prompt is a numbered Q1..QN block asking for A1..AN-shaped replies; a regex parser extracts each answer back into per-question rows. Per-batch latency and `injected_tokens` are distributed evenly across the questions in the batch.
- **Configuration in this benchmark:** CLI flags `--pam-batch-size` and `--pam-debug-user-id`. The Mongo doc records `pam_user_id`, `pam_batch_size`, and `memory_creation_duration_sec` per sample. Pam-internal model/retrieval config is not exposed by the API.
- **Secrets required:** `PAM_API_HOST`, `PAM_API_USER`, `PAM_API_PASSWORD` (admin credentials). Loaded from `secrets.env` locally; from Secret Manager on Cloud Run.
- **Cost & latency profile:** Pam is internal infra — `est_cost_usd` is recorded as `0.0`. Latency rows in Mongo reflect SSE round-trip time divided by batch size. `memory_creation_duration_sec` is the dominant cost per sample (single-digit minutes).
- **Token accounting:** `injected_tokens` (from Pam's SSE `usage`) tracks how many tokens the retriever fed to the answering model — the closest analog to "input tokens" for a memory product. `input_tokens` is left at 0 (Pam does not expose the underlying LLM's input-token count). `output_tokens` is estimated by tokenizing each answer with `cl100k_base` for cross-baseline comparability.
- **License / ToS:** Harmix-internal. Published comparisons follow [[licensing-and-data-handling]].
- **Caveats:** Pam's memory-build is a long-poll background job; transient poll errors are tolerated up to 3 in a row before the sample is marked failed. The full Pam stack (backbone model, embedding model, retriever) can change between releases — record the Pam release in `exp_name` (e.g. `locomo_pam_2026_05_24`).
- **Date of last evaluation:** N/A until M2 acceptance run is published.

---

_Placeholder cards for the M4–M5 memory competitors (Honcho, Supermemory, mem0, Zep, Claude Code + Memory.md, Claude Code + Obsidian, OpenClaw + .md) will be added when each is integrated._
