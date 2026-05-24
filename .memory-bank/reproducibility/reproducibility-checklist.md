# Reproducibility Checklist

Adapted from the NeurIPS Reproducibility Checklist + ML Reproducibility Checklist (Pineau et al.). Per the rewrite-plan methodology — used internally as a gate before any externally published number, not as a paper-submission artifact.

## Code & Data

- [x] Code repository with a clear entry point — `scripts/run_benchmark.py`
- [ ] Dataset accessible to anyone who needs to run the benchmark — LoCoMo file gitignored; obtain from https://github.com/snap-research/locomo (TODO: document recommended internal mirror in [[hosting-and-versioning]])
- [x] Pinned dependency lockfile — `uv.lock`
- [x] Container image — `cluster/Dockerfile` (digest recorded per run in the Mongo doc's `image_digest`)
- [x] Deterministic data verification script — `scripts/download_data.py` (verifies presence; sha256 checksum TODO before M2)

## Experiments

- [x] All hyperparameters reported — captured in `RunConfig`, persisted to `outputs/<exp>/<seed>/config.yaml` and to the Mongo doc's `baseline_kwargs`/`judge_model`/`seed`.
- [x] Number of seeds reported — `seed` field on every Mongo doc. M1 = 1 seed; M2 target ≥ 3.
- [x] Hardware reported — for hosted-API runs we record `image_digest`; the GCP region runs on Cloud Run Jobs (CPU-only).
- [x] Wall-clock time and cost per experiment — `execution_time_seconds`, `total_cost_usd` per doc.
- [x] Evaluation scripts produce numbers stable across re-runs at the same `--seed` — verified via the M1 acceptance run (`gpt-4-turbo` × LoCoMo, seed 42); re-run on the same image digest reproduces `qa_responses[*].f1_score` exactly.

## Results

- [x] Central tendency + dispersion reported — single-seed in M1 (dispersion deferred to M2 multi-seed).
- [ ] Statistical significance tests where claims are comparative — deferred to M2 (M1 has no comparison).
- [x] Per-slice / subgroup results — per-category F1 + judge accuracy on every doc.
- [x] Negative / null results recorded — `qa_responses` carries every question, including incorrect ones.

## Dataset

- [x] Datasheet provided — [[datasheet]]
- [x] License clearly stated — [[licensing-and-data-handling]]
- [x] Maintenance plan — [[hosting-and-versioning]]
