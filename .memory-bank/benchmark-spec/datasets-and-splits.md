# Datasets & Splits

Full datasheet at [[datasheet]].

## Datasets

| Dataset | Version | # Samples | # Questions | License | Source | Status |
|---|---|---|---|---|---|---|
| LoCoMo | 1.0 | 10 | ~2000 | Upstream — see source repo for terms | https://github.com/snap-research/locomo | **Active (M1)** |
| LongMemEval | — | — | — | — | upstream | Slot reserved (M7) |
| MEMTRACK | — | — | — | — | internal | Slot reserved (M2+) |
| BEAM | — | — | — | — | upstream | M3 priority |
| DRBench | — | — | — | — | upstream | M3 priority |
| MemoryAgentBench | — | — | — | — | upstream | M7 |

## Splits

LoCoMo ships as 10 fixed samples without a train/val/test partition. Everything is used as a test set; the framework keeps a single `test` split for now. Multi-seed = re-run with different `--seed` (controls category-5 (a)/(b) ordering and provider-side sampling where supported).

## Contamination & Leakage Audit

- **Contamination risk:** unknown overlap with `gpt-4-turbo`'s training data. The LoCoMo paper documents the source generation pipeline; samples are synthetic conversations seeded from personas, so verbatim presence on the public web is unlikely but not measured.
- **Audit method:** not run for M1; flagged for M2 (run dedup against a recent Common Crawl sample).
- **No data ever flows into training:** baselines we control (PAM, our LLM configs) MUST NOT train or fine-tune on LoCoMo data. Enforced by policy + by never exposing labels at inference.

## Data Statement / Provenance

See [[datasheet]] for the full datasheet. Top-line:
- Multi-session English conversations between two personas, with multiple-day timelines.
- Per-question category labels (1–5) and evidence pointers (`D{session}:{turn}`).
- Synthetic; no PII from real individuals.
