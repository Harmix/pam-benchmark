# Pam baseline

The in-house Pam memory baseline. Wraps Pam's HTTP API in the `Baseline`
protocol so the same harness that runs `gpt-4-turbo` can run Pam end-to-end.

## How it slots into the harness

```
setup                  → admin login (once per run)
prepare_for_sample     → create user → process-generic-files (upload + trigger memory) → poll status until completed
answer_batch           → 1 SSE call per chunk of N questions (default N=10) with numbered Q1..QN/A1..AN protocol
cleanup_sample         → delete the just-finished conversation's user account
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
4. `POST /v1/messages/stream` — one SSE call per batch of questions. Prompts use a numbered `Q1..QN / A1..AN` protocol; the reply is parsed back into per-question rows.
5. `DELETE /v1/admin/delete-account/{user_id}?backup_memory={true|false}` — issued via the admin token immediately after the last batch completes, before the next conversation begins. The `backup_memory` query param comes from `--backup-memory`: when `true`, Pam preserves the user's GCS memory directory after deletion (everything else — DB rows, VM user, files — is still wiped). One account = one uploaded conversation = one built memory, so Pam never holds multiple memory versions for the same user.

The serializer (`serialize.py`) emits **one JSON file per LoCoMo sample**
preserving the original session order from `src/datasets/locomo/data/locomo10.json`.
Pam ingests that single file and builds one memory per sample; all of the
sample's questions are answered against that one memory.

## Flags

| Flag | Default | Meaning |
|---|---|---|
| `--baseline pam` | — | Select this baseline |
| `--pam-batch-size N` | `10` | Questions per SSE call |
| `--pam-debug-user-id ID` | (off) | Reuse an existing Pam user; skips create / upload / memory build |
| `--backup-memory` | off | Forwarded as `?backup_memory=true` on the per-conversation `DELETE /v1/admin/delete-account/{user_id}` call. When set, Pam preserves the user's GCS memory directory after deletion (all other records are still wiped). |

## Environment

Required in `secrets.env`:

```
PAM_API_HOST=...
PAM_API_USER=...
PAM_API_PASSWORD=...
```

## Metrics

Per-question rows in Mongo carry `injected_tokens` (from Pam's SSE `usage`)
and `output_tokens` (estimated via tiktoken for cross-baseline comparability).
`input_tokens` and `est_cost_usd` stay at 0 — Pam doesn't expose the
underlying LLM's input-token count, and Pam is internal infra so per-token
cost is not the right unit.

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
