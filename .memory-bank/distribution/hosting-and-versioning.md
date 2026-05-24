# Hosting & Versioning

## Hosting

| Artifact | Primary Host | Backup | Notes |
|---|---|---|---|
| Code | GitHub (this repo) | Local clones | Internal repo. Tags mark milestones (M1 → tag `m1`). |
| LoCoMo data | not hosted by us | upstream GitHub | Obtain from https://github.com/snap-research/locomo |
| Container image | GCP Artifact Registry `${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/${AR_REPO}/pam-benchmark` | — | Built + pushed by `cluster/deploy.sh` |
| Results | MongoDB (collection `<dataset>_results`, e.g. `locomo_results`) | none | Single source of truth for metrics |
| Reports | local `reports/<exp-name>/` (gitignored) | regenerated on demand | `scripts/generate_report.py --exp-name <name>` |

## Versioning Policy

- **Code:** semantic versioning starting at v0.1.0 (M1). Bump minor for M2/M3/etc.
- **Data:** LoCoMo v1.0 (upstream); add a `data_version` if a future M2+ dataset version is published. M1 doesn't surface this field yet; add it when the second dataset lands.
- **Image:** tagged by git short SHA via `cluster/deploy.sh`. Each Mongo doc records the resolved `image_digest` for full provenance.
- **Changelog:** TBD — add a `CHANGELOG.md` when M2 work starts and a second milestone exists to log.

## Maintenance

- **Owner:** Denys (Harmix).
- **Triage SLA:** broken download / scoring bug → fix before next external claim; vendor-API drift → re-run quarterly.
- **Re-run cadence for hosted-API competitors:** quarterly; record `baseline_kwargs.model` snapshot per run so drift is visible. Tied to Pam ([manager.harmix.ai](https://manager.harmix.ai)) release cadence — every Pam release also re-runs the benchmark for regression detection.
