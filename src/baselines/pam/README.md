# Pam baseline

The in-house Pam memory baseline. Wraps Pam's HTTP API in the `Baseline`
protocol so the same harness that runs `gpt-4-turbo` can run Pam end-to-end.

## How it slots into the harness

```
setup                  → admin login (once per run)
prepare_for_sample     → create user → process-generic-files (upload + trigger memory) → poll status until completed
                         (debug mode: mint a per-user token for --pam-debug-user-id and skip the build)
answer_batch           → 1 SSE call per chunk of N questions (default N=10) with numbered Q1..QN/A1..AN protocol
cleanup_sample         → delete the just-finished conversation's user account
                         (skipped entirely when --backup-memory or --pam-debug-user-id is set)
teardown               → no-op
```

### Pam API calls, in order, for one LoCoMo conversation

1. `POST /v1/admin/create-account` — fresh user with a unique email (`locomo-<sample_id>-<ts>-<rand>@benchmark.local`); we keep the returned **per-user `access_token`** (used as the bearer on steps 2–4) plus the admin token (used on step 5).
2. `POST /v1/memory/process-generic-files/{user_id}` — multipart upload of the `<sample_id>_conversation.json` payload (max 5 files per request), sent with `Authorization: Bearer <per-user access_token>`. The endpoint zips the upload, stages it in GCS, and publishes the RunRequested Pub/Sub message. Returns `{"run_id": ..., ...}`. **Auth:** a missing token returns `401`; a token that doesn't belong to `{user_id}` returns `403`. The client refreshes once on `401` (covers expired tokens during a long build) and raises `PamAuthError` if the second attempt still fails or if any `403` comes back — these are surfaced as fatal misconfiguration, not retried.
3. `GET /v1/memory/get-memory-pipeline-status/{user_id}/{run_id}` — polled every 30s with the same `Authorization: Bearer <per-user access_token>`. The endpoint reads `pipeline_runs` for the matching `(user_id, run_id, pipeline_type='memory_pull')` row and normalizes `run_status` to one of `completed` / `failed` / `pending`. We:
   - return success when `status == "completed"`,
   - raise `RuntimeError` (with `error_stage` + `error_message`) when `status == "failed"`,
   - keep polling on anything else (`pending`, unknown, or no row yet),
   - raise `PamAuthError` immediately on `401` (after a single refresh) or `403`. The polling loop catches `PamAuthError` explicitly and re-raises so it is **never** counted toward the transient-error budget; a bad token would otherwise look like a stuck pipeline.

   Up to 3 consecutive *non-auth* transient HTTP errors are tolerated before propagating.
4. `POST /v1/messages/stream` — one SSE call per batch of questions, sent with the **per-user** access token (so Pam answers from this user's memory). Prompts use a numbered `Q1..QN / A1..AN` protocol; the reply is parsed back into per-question rows.
5. `DELETE /v1/admin/delete-account/{user_id}` — issued via the admin token immediately after the last batch completes, before the next conversation begins. This wipes the user and all of its records. **Skipped entirely when `--backup-memory` is set** — in that case the account and its built memory are preserved so they can be reused later via `--pam-debug-user-id`. Without `--backup-memory`, one account = one uploaded conversation = one built memory, so Pam never holds multiple memory versions for the same user.

### Reusing a backed-up memory (`--pam-debug-user-id`)

After a `--backup-memory` run, you can re-run the questions against an existing user's already-built memory without rebuilding it:

- `prepare_for_sample` skips create / upload / memory-build.
- It mints a **per-user** access token for that user via `POST /v1/admin/users/{user_id}/tokens`, sent with **both** the `api-key: <PAM_API_KEY>` header (the route's own gate) **and** the admin `Authorization: Bearer` token (the API edge/gateway rejects bearer-less requests with `401 Authentication required`). This is required because `POST /v1/messages/stream` answers from whichever user the bearer token belongs to; using the admin token there would query the admin's memory, not the reused user's.
- `cleanup_sample` does not delete the user.

The serializer (`serialize.py`) emits **one JSON file per LoCoMo sample**
preserving the original session order from `src/datasets/locomo/data/locomo10.json`.
Pam ingests that single file and builds one memory per sample; all of the
sample's questions are answered against that one memory.

## Flags

| Flag | Default | Meaning |
|---|---|---|
| `--baseline pam` | — | Select this baseline |
| `--pam-batch-size N` | `10` | Questions per SSE call |
| `--pam-debug-user-id ID` | (off) | Reuse an existing Pam user; skips create / upload / memory build / delete. Mints a per-user token (needs `PAM_API_KEY`) so chat runs as that user. |
| `--backup-memory` | off | Keep each conversation's account after the run (no delete-account call). The account and its built memory survive for later reuse via `--pam-debug-user-id`. |

## Environment

Required in `secrets.env`:

```
PAM_API_HOST=...
PAM_API_USER=...
PAM_API_PASSWORD=...
PAM_OUTPUT_TOKEN_MODEL=...   # model id whose tokenizer counts Pam output tokens
# Postgres holding pam.message_metrics (agent-side token usage per answer):
DATABASE_HOST=...
DATABASE_PORT=...
DATABASE_NAME=...
DATABASE_USERNAME=...
DATABASE_PASSWORD=...
```

Optional (only for `--pam-debug-user-id` reuse):

```
PAM_API_KEY=...   # Harmix API key; used to mint a per-user token for the reused user
```

If `PAM_OUTPUT_TOKEN_MODEL` is unset, `output_tokens` is reported as `0`. If the
`DATABASE_*` vars are unset or the DB is unreachable, the `agent_*` token counts
are reported as `0` (the run still completes).

## Metrics

Per-question rows in Mongo carry `injected_tokens` (from Pam's SSE `usage`),
`output_tokens` (estimated with a fixed tokenizer for cross-baseline
comparability), and `prompt_tokens` — the token count of the prompt the
benchmark sends to Pam (the rendered `Q1..QN` batch, split evenly across its
questions; always > 0). `input_tokens`, `context_tokens`, and `est_cost_usd`
stay at 0 — Pam doesn't expose the underlying LLM's input-token count, and Pam
is internal infra so per-token cost is not the right unit.

After each answer the baseline reads the most-recent `pam.message_metrics` row
for the acting user and records the agent's own token usage:
`agent_input_tokens`, `agent_output_tokens`, `agent_cache_read_tokens`,
`agent_cache_write_tokens`, and `enriched_user_prompt_tokens`. A batch shares one
agent call, so each row's totals are split evenly across the batch's questions;
per-sample they are summed into the `total_agent_*` /
`total_enriched_user_prompt_tokens` fields. The row's `model_used` is recorded as
`agent_model_used` inside the Mongo doc's `baseline_kwargs`.

Per-sample rows carry `memory_creation_duration_sec`, `pam_user_id`, and
`pam_batch_size` as top-level fields (via `PamBaseline.extras()`).

## Files

```
src/baselines/pam/
├── README.md         # this file
├── baseline.py       # PamBaseline (lifecycle + batching + parser)
├── client.py         # sync PamClient (login, upload, memory polling, SSE)
└── serialize.py      # LoCoMoSample → [(filename, json_bytes)]
```
