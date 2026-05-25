# Pam baseline

The in-house Pam memory baseline. Wraps Pam's HTTP API in the `Baseline`
protocol so the same harness that runs `gpt-4-turbo` can run Pam end-to-end.

## How it slots into the harness

```
setup                  → admin login
prepare_for_sample     → create user → upload <sample_id>_conversation.json → trigger + poll memory pipeline
answer_batch           → 1 SSE call per chunk of N questions (default N=10) with numbered Q1..QN/A1..AN protocol
cleanup_sample         → delete user
teardown               → no-op
```

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
