# Datasheet — LoCoMo (M1)

Per Gebru et al., "Datasheets for Datasets" (2021). LoCoMo is the only active dataset in M1; new datasets will get their own datasheet section here as they're added.

## Motivation

- **Purpose:** Evaluate very long-term conversational memory in LLMs.
- **Authors:** Snap Inc. research team. See paper: https://aclanthology.org/2024.acl-long.747.pdf
- **Funding:** Snap Inc.

## Composition

- **Instances:** 10 synthetic multi-session conversations between two personas, with ~150–200 QA pairs each (≈ 2000 total).
- **Sample fields:** `sample_id`, `qa` (list of `{question, answer | adversarial_answer, evidence, category}`), `conversation` (`speaker_a`, `speaker_b`, and `session_{i}` / `session_{i}_date_time` keys), plus auxiliary `event_summary`, `observation`, `session_summary` we currently ignore.
- **Sampling:** small fixed test set; the paper documents the generation pipeline.
- **Missing data:** category-5 questions may lack a canonical `answer` (use `adversarial_answer`).
- **Recommended splits:** none — all 10 samples are used as the test set.
- **Errors / noise:** a handful of integer-typed `answer` fields (years, counts) appear in the JSON; the loader coerces these to strings to keep downstream scoring uniform.
- **Self-contained:** yes — single JSON file.
- **Sensitive content:** synthetic personas; no real-person PII. Edge-case content (e.g. adversarial false premises) is handled by the category-5 protocol.

## Collection Process

- **Acquisition:** synthetic generation by the LoCoMo authors per their paper's pipeline.
- **Annotators:** see paper. No additional annotation by us.
- **Timeframe:** documented in the paper.
- **Ethical review:** N/A (synthetic data).

## Preprocessing / Cleaning

- We don't preprocess upstream JSON. Field-level normalization (coercing int → str for `answer`) happens at load time in `src/datasets/locomo/schemas.py`.

## Uses

- **Already used for:** the paper's published baseline evaluations.
- **Our internal use:** M1 baseline check + ongoing regression detection for any baseline we add.
- **Should NOT be used for:** training or fine-tuning baselines we evaluate on it.

## Distribution

- **Internal access:** dataset file lives at `src/datasets/locomo/data/locomo10.json` (gitignored). Obtain from https://github.com/snap-research/locomo per upstream terms.
- **External redistribution:** not by us — point external consumers at the upstream repo.

## Maintenance

- **Owner:** Denys (until a successor is named).
- **Issue reporting:** via repo issues / Slack.
- **Update cadence:** upstream-driven; we pin our copy by `sha256` (TODO: add to `scripts/download_data.py` before M2).
- **Retention:** indefinite; LoCoMo is a public synthetic corpus.
