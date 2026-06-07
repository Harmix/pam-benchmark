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
- **Integration:** `src/baselines/pam/` — see `src/baselines/pam/README.md` for the full integration map.

#### How the benchmark drives Pam (one LoCoMo conversation)

For each of the 10 LoCoMo conversations the harness executes the following calls in order:

| # | Pam endpoint | Purpose |
|---|---|---|
| 1 | `POST /v1/admin/create-account` | Mint a fresh per-conversation user. Email is `locomo-<sample_id>-<ts>-<rand>@benchmark.local`. The returned **per-user `access_token`** is the bearer for steps 2–4; the admin token is reserved for step 5. (In `--pam-debug-user-id` mode this step is replaced by `POST /v1/admin/users/{user_id}/tokens` to mint a per-user token for the reused user.) |
| 2 | `POST /v1/memory/process-generic-files/{user_id}` | Multipart upload of one `<sample_id>_conversation.json` (preserving the original session order from `locomo10.json`), sent with `Authorization: Bearer <per-user access_token>`. Max 5 files per request — for LoCoMo we always send exactly 1. Endpoint zips, stages in GCS, publishes the RunRequested Pub/Sub message, and returns `{"run_id": ..., ...}`. Auth: missing token → `401`, mismatched user → `403`; the client refreshes once on `401` (covers token expiry mid-run) and then raises `PamAuthError` as fatal — distinct from any pipeline error. |
| 3 | `GET /v1/memory/get-memory-pipeline-status/{user_id}/{run_id}` | Polled every 30 s with the same per-user bearer. The endpoint reads `pipeline_runs` for the matching `(user_id, run_id, pipeline_type='memory_pull')` row and normalizes `run_status` to `completed` / `failed` / `pending`. The harness blocks on `pending`, raises `RuntimeError` (with `error_stage` + `error_message`) on `failed`, and proceeds on `completed`. `401`/`403` are raised as `PamAuthError` immediately and are **never** counted toward the transient-error budget — a misconfigured token must not look like a stuck pipeline. Up to 3 consecutive *non-auth* HTTP errors are absorbed before propagating. |
| 4 | `POST /v1/messages/stream` (repeated) | One SSE call per chunk of `--pam-batch-size` questions (default 10). The prompt is a numbered `Q1..QN` block asking for `A1..AN`-shaped replies; a regex parser splits the reply into per-question rows. Per-batch latency and `injected_tokens` are distributed evenly across the questions in the batch. |
| 5 | `DELETE /v1/admin/delete-account/{user_id}` | Issued via the admin token immediately after the last batch for this conversation completes, before the next conversation begins — wipes the user and all of its records. **Skipped entirely when `--backup-memory` is set**, so the account and its built memory are preserved for later reuse via `--pam-debug-user-id`. Without `--backup-memory`, each Pam user stays single-purpose: **one account = one uploaded conversation = one built memory**. |

The harness moves to the next LoCoMo conversation and repeats steps 1–5. There is no cross-conversation state on the Pam side, so the 10 runs are fully isolated.

**Reusing a backed-up memory (`--pam-debug-user-id`).** After a `--backup-memory` run, the questions can be replayed against an existing user's already-built memory: the harness skips create/upload/memory-build (and the delete), and mints a **per-user** access token for that user via `POST /v1/admin/users/{user_id}/tokens` (sent with both the `api-key: <PAM_API_KEY>` header and the admin `Authorization: Bearer` token — the API edge rejects bearer-less requests). This is required because `POST /v1/messages/stream` answers from whichever user the bearer token belongs to — the admin token would query the wrong memory.

- **Configuration in this benchmark:** CLI flags `--pam-batch-size`, `--pam-debug-user-id`, `--backup-memory`. The Mongo doc records `pam_user_id`, `pam_batch_size`, `pam_memory_run_ids`, and `memory_creation_duration_sec` per sample. Pam-internal model/retrieval config is not exposed by the API.
- **Secrets required:** `PAM_API_HOST`, `PAM_API_USER`, `PAM_API_PASSWORD` (admin credentials), and `PAM_OUTPUT_TOKEN_MODEL` (model id whose tokenizer counts Pam's output tokens — kept out of source). `PAM_API_KEY` (Harmix API key) is additionally required only for `--pam-debug-user-id` reuse (minting a per-user token). Loaded from `secrets.env` locally; from Secret Manager on Cloud Run.
- **Cost & latency profile:** Pam is internal infra — `est_cost_usd` is recorded as `0.0`. Latency rows in Mongo reflect SSE round-trip time divided by batch size. `memory_creation_duration_sec` is the dominant cost per sample (single-digit minutes).
- **Token accounting:** `injected_tokens` (from Pam's SSE `usage`) tracks how many tokens the retriever fed to the answering model — the closest analog to "input tokens" for a memory product. `input_tokens` is left at 0 (Pam does not expose the underlying LLM's input-token count), so `prompt_tokens` and `context_tokens` are 0 as well. `output_tokens` is estimated by tokenizing each answer with a fixed tokenizer for cross-baseline comparability.
- **License / ToS:** Harmix-internal. Published comparisons follow [[licensing-and-data-handling]].
- **Caveats:** Pam's memory-build is a long-poll background job; transient (non-auth) poll errors are tolerated up to 3 in a row before the sample is marked failed. Auth failures (`401` after one refresh / any `403`) are raised as `PamAuthError` and fail the sample immediately — they cannot be confused with a stuck pipeline. The full Pam stack (backbone model, embedding model, retriever) can change between releases — record the Pam release in `exp_name` (e.g. `locomo_pam_2026_05_24`).
- **Date of last evaluation:** N/A until M2 acceptance run is published.

---

_Placeholder cards for the M4–M5 memory competitors (Honcho, Supermemory, mem0, Zep, Claude Code + Memory.md, Claude Code + Obsidian, OpenClaw + .md) will be added when each is integrated._
