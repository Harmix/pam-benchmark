# Compute & Environment

## Hardware

| Experiment | Accelerator / API | Count | Wall-clock | Cost |
|---|---|---|---|---|
| M1 acceptance (LoCoMo × gpt-4-turbo, all 10 samples) | OpenAI hosted API (gpt-4-turbo) + gpt-4o judge | — | TBD | TBD |

Cloud Run Jobs container = CPU-only `python:3.12-slim`; no GPUs. Compute cost is dominated by OpenAI API spend, not GCP compute.

## Software Environment

- **Python:** 3.12 (pinned in `.python-version`, enforced by `pyproject.toml`).
- **Package manager:** `uv` (>= 0.5).
- **Key libraries:** `litellm`, `instructor`, `pydantic>=2`, `typer`, `rich`, `tenacity`, `aiolimiter`, `tiktoken`, `pymongo`, `asyncpg` (reads Pam's `message_metrics`), `jinja2`, `pandas`, `numpy`, `nltk` (Porter stemmer for F1), `regex`, `scipy`.
- **Lockfile:** `uv.lock` (committed). Hash of the lock is recorded per run in the Mongo doc's `uv_lock_hash`.
- **Container:** `cluster/Dockerfile` (base `python:3.12-slim`). Per-run image digest in the Mongo doc's `image_digest`.

## Determinism

- **Seeds:** `--seed` (default 42) seeds Python `random`, NumPy, and is passed to LiteLLM's `seed` extra arg (provider-supported determinism on OpenAI).
- **Category-5 (a)/(b) randomization:** seeded per `(seed, sample_id, question)` so two runs with the same `--seed` see identical option layouts.
- **Provider-side non-determinism:** hosted APIs (OpenAI, etc.) can drift silently. Per-run `baseline_kwargs.model` records the exact model id; periodic blind re-runs are the mitigation (M2 work).
- **Tolerance:** F1 should be bit-exact between two same-seed runs on the same provider snapshot; LLM-judge may flip a few records on edge cases.

## Verifying a reproduction

A fresh checkout + `uv sync --frozen` + `docker build -f cluster/Dockerfile` should produce an image whose digest matches what's in the Mongo doc. Re-run the same `--exp-name --seed` and the F1 should match exactly; LLM-judge accuracy should be within ±1 pp.
