# Run & Submission Process

## How a baseline gets evaluated

1. A Harmix engineer configures the baseline (M1: `gpt-4-turbo`; M2: Pam via [manager.harmix.ai](https://manager.harmix.ai); M4–M5: each competitor) following [[evaluation-protocol]].
2. Invokes `scripts/run_benchmark.py` with a stable `--exp-name`. For multi-seed: re-invoke N times with different `--seed`.
3. The runner writes one Mongo doc per `(exp_name, sample_id, seed)`. Local `outputs/<exp>/<seed>/{config.yaml, metrics.json}` mirror the aggregates.
4. `scripts/generate_report.py --exp-name <name>` renders the HTML report to `reports/<name>/report.html`.
5. A second Harmix engineer reviews `config.yaml` + a sample of `qa_responses` records before any external use.

## Provenance captured per run (in every Mongo doc)

- `exp_name`, `sample_id`, `seed`, `baseline`, `baseline_kwargs`, `judge_model`
- `dataset_name`, `task_name`
- All aggregate metrics + the full `qa_responses` nested array
- `git_commit`, `image_digest`, `uv_lock_hash` (provenance)
- `timestamp`, `created_at`

Every number in any report, slide, or external doc must be traceable to a captured run via `exp_name`.

## Anti-bias measures

- Same data version, same scoring-script commit, same `--exp-name` for every baseline in a head-to-head.
- Same `--judge-model` for any pairwise comparison; record in the Mongo doc.
- Periodic blind re-runs of hosted-API competitors to detect drift.
- Spot-audit: a random sample of LLM-judge verdicts are hand-verified by a human reviewer monthly.

## Releasing numbers externally

Per [[licensing-and-data-handling]] external-claim policy:
1. Vendor ToS check.
2. Engineering-lead sign-off.
3. Required context attached (exp_name, seed(s), image digest/commit, date, judge model, dispersion).
4. Logged in the Harmix audit Slack channel so we can re-issue/retract on drift.

M1 numbers are NOT publishable externally (single seed; no dispersion). M2 — the first multi-seed milestone with Pam in the mix — is the earliest whose numbers can appear in a Harmix slide deck, blog post, or [manager.harmix.ai](https://manager.harmix.ai) collateral.
