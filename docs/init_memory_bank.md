---
description: Initialize a .memory-bank folder with structured documentation templates for an internal ML benchmark comparing our solution against competitors, built on top-tier methodological foundations
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion
---

Initialize a Memory Bank for an **internal ML benchmark** whose primary purpose is to compare our company's solution against competing solutions on tasks we care about. The methodology is held to the standard of top ML conferences (NeurIPS, ICML, ICLR) so that results are defensible internally and externally, but the templates do **not** assume an academic submission.

Memory Bank is a `.memory-bank` folder in the project root that serves as the persistent knowledge base for the benchmark's motivation, task/dataset/metric specifications, evaluation protocol, baseline competitors and our system, reproducibility plan, ethics and licensing, and ongoing experiments.

The templates here are aligned with community standards so the results stand up to scrutiny:
- **Datasheets for Datasets** (Gebru et al., 2021)
- **Model Cards for Model Reporting** (Mitchell et al., 2019)
- **Reproducibility checklists** (Pineau et al.; NeurIPS / ML reproducibility)
- **Croissant** dataset metadata for machine-readable distribution
- Multi-seed runs with dispersion and significance testing
- Disclosure of compute, environment, seeds, and broader impacts

## Steps

### 1. Check for existing Memory Bank

Look for an existing `.memory-bank` folder in the project root. If one exists, inform the user and ask whether to overwrite, merge, or skip.

### 2. Analyze the project

Before creating files, analyze the current project to pre-fill templates with real data:

- **Project metadata**: `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements*.txt`, `environment.yml`, `package.json` — name, version, authors, license
- **ML stack signals**: presence of `torch`, `transformers`, `datasets`, `lightning`, `jax`, `flax`, `tensorflow`, `scikit-learn`, `numpy`, `pandas` in deps; CUDA / accelerator hints in configs
- **Benchmark structure**: `datasets/`, `data/`, `tasks/`, `benchmarks/`, `eval/`, `evaluation/`, `baselines/`, `models/`, `scripts/`, `configs/` directories; YAML/JSON task configs; registry files
- **Existing dataset registries / cards**: `README` files inside dataset folders, `datasheet*.md`, `*_card.md`, `croissant*.json`, `metadata*.json`
- **Evaluation harness**: scripts named `eval*`, `run_benchmark*`, `score*`, `leaderboard*`; pytest configs and test commands
- **Competitor / baseline integrations**: adapter folders, API clients, vendored SDKs, names of competing products in configs
- **Reproducibility hints**: pinned lockfiles (`uv.lock`, `poetry.lock`, `requirements.lock`), Dockerfiles, Makefiles, fixed random seeds in code, `conda-lock`
- **CI / infra**: `.github/workflows`, `.gitlab-ci.yml`, container build files; experiment tracking (W&B, MLflow, TensorBoard) in deps
- **Licensing**: `LICENSE`, `LICENSE-DATA`, `NOTICE`, per-dataset license files; SPDX identifiers
- **Git conventions**: branch names, recent commit message style

### 3. Create folder structure

Create the following structure:

```
.memory-bank/
├── index.md
├── benchmark-overview/
│   ├── README.md
│   ├── goals-and-questions.md
│   └── scope-and-related-work.md
├── benchmark-spec/
│   ├── README.md
│   ├── tasks-and-metrics.md
│   ├── datasets-and-splits.md
│   └── evaluation-protocol.md
├── baselines/
│   ├── README.md
│   ├── system-cards.md
│   └── results.md
├── reproducibility/
│   ├── README.md
│   ├── reproducibility-checklist.md
│   ├── compute-and-environment.md
│   └── statistical-reporting.md
├── ethics-and-licensing/
│   ├── README.md
│   ├── datasheet.md
│   └── licensing-and-data-handling.md
├── distribution/
│   ├── README.md
│   ├── hosting-and-versioning.md
│   └── run-and-submission-process.md
└── tasks/
    ├── README.md
    ├── active.md
    └── backlog.md
```

### 4. Fill templates with project data

Use the templates below. Replace placeholder values with real data discovered in step 2. Leave sections as templates (with placeholder text) only when no data can be inferred.

#### index.md

```markdown
# [Benchmark Name] - Memory Bank

A persistent knowledge base for the [Benchmark Name] benchmark — the framework we use
to compare our solution against competing solutions on the tasks our customers care about.

## Quick Links

- [Benchmark Overview](./benchmark-overview/README.md) — goals, questions, scope
- [Benchmark Spec](./benchmark-spec/README.md) — tasks, datasets, metrics, protocol
- [Baselines](./baselines/README.md) — our system + competitors, results
- [Reproducibility](./reproducibility/README.md) — checklist, environment, statistics
- [Ethics & Licensing](./ethics-and-licensing/README.md) — datasheet, data handling
- [Distribution](./distribution/README.md) — hosting, versioning, how runs happen
- [Tasks](./tasks/README.md) — active work and backlog

## Benchmark Summary

One paragraph: what the benchmark measures, which decisions it supports
(product positioning, model selection, regression detection, customer-facing claims),
and what would make a result "good enough to act on".

## Audience for Results

- **Internal**: product, engineering, leadership — who reads these results, what they
  do with them.
- **External (optional)**: customers, prospects, analysts — what subset of results we
  publish and under what conditions.

## Current Status

- **Phase**: Design / Data collection / Baselines / Stable / Maintenance
- **Version**: vX.Y.Z (semver; data and code versioned independently if needed)
- **Last Updated**: YYYY-MM-DD
```

#### benchmark-overview/README.md

```markdown
# Benchmark Overview

## What is [Benchmark Name]?

2–3 sentences describing what the benchmark evaluates and on what data.

## Why this benchmark exists

What decision does it support? Examples:
- Should we ship feature X given competitor Y?
- Are we regressing on capability Z release-over-release?
- Which model / configuration of our system performs best on customer workloads?
- Can we make a defensible public claim about our system vs. alternatives?

Why existing public benchmarks are insufficient for this decision (saturation, wrong domain,
contamination, missing capability, unrealistic distribution, etc.).

## Scope

- **In scope**: tasks, modalities, domains, languages, system families covered.
- **Out of scope**: explicitly enumerate what this benchmark does *not* claim to measure,
  so internal stakeholders do not over-extrapolate.

## Intended Use

- Who uses these results internally and how (product, engineering, leadership, sales).
- Misuse to avoid (e.g., cherry-picking a single task, single-seed claims, comparing
  across different benchmark versions).

## Success Criteria for the Benchmark Itself

- The benchmark is reproducible by an engineer who did not build it.
- Re-running the same system against the same version gives the same numbers within
  documented tolerance.
- Differences flagged as "significant" survive a second independent run.
- New systems can be added without re-implementing the harness.
```

#### benchmark-overview/goals-and-questions.md

```markdown
# Goals & Questions

State the questions the benchmark is designed to answer. Each question should be
falsifiable and tied to a metric / experiment.

## Q1: [short title]

- **Question**: …
- **Why we need to answer it**: which internal decision depends on this.
- **Metric(s) that answer it**: …
- **Experiment design**: …
- **What "good" looks like**: threshold or comparative claim that would change a decision.

## Q2: …

## Explicit Non-Questions

What this benchmark does *not* try to answer. Manages internal expectations and prevents
stakeholders from quoting numbers outside their valid scope.
```

#### benchmark-overview/scope-and-related-work.md

```markdown
# Scope & Related Work

## What our benchmark adds

Enumerate 3–5 concrete things this benchmark gives us that we could not get from existing
public benchmarks or anecdote.

1. **[Item]** — what is new, and why it matters for our decisions.
2. …

## Related Public Benchmarks

| Benchmark | Year | Task / Domain | Why It Doesn't Cover Our Need | Reference |
|-----------|------|---------------|--------------------------------|-----------|
| …         | …    | …             | …                              | …         |

## Positioning Statement

One paragraph: "Unlike [X, Y, Z], our benchmark …". This is the paragraph we'd use when
explaining to a new hire or a customer why we built our own.
```

#### benchmark-spec/README.md

```markdown
# Benchmark Specification

The technical contract of the benchmark. Anything here is load-bearing for reproducibility
and for cross-system comparability.

- [Tasks & Metrics](./tasks-and-metrics.md)
- [Datasets & Splits](./datasets-and-splits.md)
- [Evaluation Protocol](./evaluation-protocol.md)
```

#### benchmark-spec/tasks-and-metrics.md

```markdown
# Tasks & Metrics

## Tasks

### Task 1: [name]

- **Input format**: …
- **Output format**: …
- **Task definition** (formal): …
- **Why this task**: links to question in [[goals-and-questions]].

## Metrics

| Metric | Range | Higher is Better | Primary? | Definition / Reference |
|--------|-------|------------------|----------|------------------------|
| …      | …     | yes/no           | yes/no   | …                      |

### Metric Aggregation

- How per-example scores are aggregated (macro/micro/weighted).
- How per-task scores are aggregated into an overall score (if any) — and the rationale.
- Tie-breaking rules.

### Known Metric Limitations

Honest disclosure of what each metric does *not* capture (e.g., exact-match and paraphrase,
accuracy and calibration, latency and quality trade-offs). Prevents over-reading results.
```

#### benchmark-spec/datasets-and-splits.md

```markdown
# Datasets & Splits

For the full datasheet (provenance, consent, PII, etc.) see [[datasheet]].

## Datasets

| Dataset | Version | # Examples | License | Source | Internal/External |
|---------|---------|------------|---------|--------|-------------------|
| …       | …       | …          | …       | …      | …                 |

## Splits

| Split | Purpose | # Examples | Stratification | Shared with vendors? |
|-------|---------|------------|----------------|----------------------|
| dev   | tuning, internal iteration | … | … | no |
| test  | reported numbers | … | … | inputs only, labels held |

## Contamination & Leakage Audit

- Overlap checks against common pretraining corpora (Common Crawl, The Pile, RedPajama, etc.)
  where competitor models are known or suspected to have trained.
- N-gram / hash-based dedup methodology.
- Date cutoffs and temporal holdout.
- For our own system: rule that benchmark data never enters training/fine-tuning data,
  and how that rule is enforced.

## Data Statement / Provenance Summary

Pointer to [[datasheet]]. Top-line items here: collection period, languages, domain,
whether examples derive from real customer data and how they were sanitized.
```

#### benchmark-spec/evaluation-protocol.md

```markdown
# Evaluation Protocol

## Allowed / Disallowed Resources

- **Allowed at inference**: tools, retrieval corpora, scratchpad, etc.
- **Disallowed**: test labels, external APIs that may have seen test data, ensembling rules.
- **Configuration rules**: prompt templates, temperature, max tokens, retries — fixed
  per system or tuned per system (document which, and why).

## Run Format

- File schema (JSONL / CSV / Parquet) and example.
- Required fields per prediction (id, prediction, optional confidence, optional rationale,
  latency, cost, tokens).

## Scoring

- Reference implementation: `[path to scoring script]`.
- Deterministic? If not, document seeded behavior.
- Per-example, per-task, and aggregate outputs.

## Configurations / Tracks (if applicable)

Use tracks when systems aren't directly comparable in a single setting (e.g., zero-shot vs.
fine-tuned, hosted API vs. self-hosted). Each track defines a fair-comparison setting.

| Track | Constraints | When to use |
|-------|-------------|-------------|
| Out-of-the-box | Default settings, no per-task tuning | "What does a customer get on day one?" |
| Tuned         | Per-task prompt/config tuning allowed  | "What is each system capable of with effort?" |

## Comparison Fairness Rules

- Same data version, same scoring script commit for every system in a comparison.
- Same compute budget per query where applicable (e.g., token budget, retries).
- Document any system-specific deviations and why they were necessary.
```

#### baselines/README.md

```markdown
# Baselines

Our system plus the competitors / baselines we compare against. We document each one to the
same standard so comparisons are defensible.

- [System Cards](./system-cards.md) — model card per baseline (ours + competitors)
- [Results](./results.md)
```

#### baselines/system-cards.md

```markdown
# System Cards

One card per baseline (our solution and each competitor), adapted from Mitchell et al. (2019)
"Model Cards for Model Reporting". For closed competitors, fill what is publicly known and
flag the rest as "undisclosed".

## Baseline: [name]

- **Identity**: vendor, product name, version / API date, checkpoint or endpoint URL.
- **Type**: ours / competitor / open-source baseline / trivial baseline (random, majority).
- **Architecture & params** (where known): …
- **Training data** (summary, where known): …
- **Intended use**: what the vendor markets it for; how that maps to our tasks.
- **Out-of-scope use**: per vendor docs.
- **Configuration used in this benchmark**: prompts, temperature, retries, tools — exact
  values so the run is reproducible.
- **Cost & latency profile**: $/1k requests, median + p95 latency observed in our runs.
- **License / terms of service**: commercial-use status, data-handling terms (does the
  vendor train on inputs?), whether we are allowed to publish comparative numbers.
- **Metrics on this benchmark**: link to [[results]].
- **Known failure modes / caveats**.
- **Date of last evaluation**: vendor systems change; record when we last re-ran.
```

#### baselines/results.md

```markdown
# Results

Report mean ± std (or 95% CI) across ≥ 3 seeds / runs. Single-run numbers are not
acceptable for any claim that drives a decision. See [[statistical-reporting]].

## Headline Comparison

| System | Track | Metric₁ (↑/↓) | Metric₂ (↑/↓) | Cost / 1k | p50 Latency | Runs | Date |
|--------|-------|---------------|---------------|-----------|-------------|------|------|
| Ours (current) | out-of-the-box | x ± s | x ± s | … | … | 5 | … |
| Competitor A   | out-of-the-box | x ± s | x ± s | … | … | 5 | … |
| Competitor B   | out-of-the-box | x ± s | x ± s | … | … | 5 | … |
| Open baseline  | out-of-the-box | x ± s | x ± s | … | … | 5 | … |
| Trivial (random / majority) | — | x ± s | x ± s | — | — | 5 | … |

## Per-Task / Per-Slice Breakdown

Include subgroup performance (by domain, customer segment, language, difficulty,
demographic when relevant). Headline averages hide the cases that matter for individual
customer pitches.

## Significance Tests

State which pairwise comparisons are significant and under what test (paired bootstrap,
permutation, McNemar) with corrections for multiple comparisons. Without this, "we beat
Competitor A by 1.2 points" is not a defensible claim.

## Release-over-Release Tracking (Our System)

| Version | Date | Metric₁ | Metric₂ | Δ vs. prev | Notes |
|---------|------|---------|---------|------------|-------|

Used to detect regressions and quantify each release's contribution.

## Headroom

Gap between the best system and a human / oracle / theoretical ceiling. If everyone is
saturated, the benchmark is no longer useful for differentiation and should be revised.
```

#### reproducibility/README.md

```markdown
# Reproducibility

- [Reproducibility Checklist](./reproducibility-checklist.md)
- [Compute & Environment](./compute-and-environment.md)
- [Statistical Reporting](./statistical-reporting.md)

The benchmark must be reproducible by another engineer on the team using only the code,
data, configs, and container image — without asking the original author for tribal
knowledge. Reproducibility is what lets results survive personnel changes and lets us
defend numbers months after they were produced.
```

#### reproducibility/reproducibility-checklist.md

```markdown
# Reproducibility Checklist

Adapted from the NeurIPS Reproducibility Checklist and ML Reproducibility Checklist
(Pineau et al.). Mark each item Y / N / N/A with a pointer to the artifact.

## Code & Data

- [ ] Code repository with a clear entry point — `[link]`
- [ ] Dataset accessible to anyone who needs to run the benchmark — `[link]`
- [ ] Pinned dependency lockfile — `[path]`
- [ ] Container image (Docker / Apptainer) — `[link]`
- [ ] Deterministic data download / preparation script with checksums — `[path]`

## Experiments

- [ ] All hyperparameters reported (with search ranges if tuned)
- [ ] Number of seeds / runs and how seeds were selected
- [ ] Hardware reported (GPU model, count, memory, interconnect, or "hosted API: vendor X")
- [ ] Wall-clock time and total compute cost per experiment
- [ ] Evaluation scripts produce identical numbers to those in [[results]] from raw model outputs

## Results

- [ ] Central tendency *and* dispersion reported (mean ± std or CI)
- [ ] Statistical significance tests where claims are comparative
- [ ] Per-slice / subgroup results where applicable
- [ ] Negative / null results recorded when relevant

## Dataset

- [ ] Datasheet provided — [[datasheet]]
- [ ] License clearly stated — [[licensing-and-data-handling]]
- [ ] Maintenance plan — [[hosting-and-versioning]]
```

#### reproducibility/compute-and-environment.md

```markdown
# Compute & Environment

## Hardware Used

| Experiment | Accelerator / API | Count | Wall-clock | GPU-hours | $ Cost |
|------------|-------------------|-------|------------|-----------|--------|
| …          | A100 80GB / vendor API | 8 | … | … | … |

Total compute for one full benchmark run (data prep + all systems + ablations): … GPU-hours,
… USD. Important for budgeting and for honest comparison (a system that is 1 point better
but 100× more expensive may not be the right pick).

## Software Environment

- Python: x.x
- Key libraries: torch x.x, transformers x.x, …
- Lockfile: `[path]`
- Container: `[registry/image:tag]`, digest `sha256:…`

## Determinism

- Seeds used: `[list]`
- Sources of nondeterminism that remain (cuDNN, scatter ops, hosted-API sampling) and how
  they were handled.
- How to verify a reproduced result matches: tolerance, comparison script.
- For hosted APIs whose behavior changes silently: record the exact date of each run and
  re-run on a documented cadence.
```

#### reproducibility/statistical-reporting.md

```markdown
# Statistical Reporting Standards

These rules apply to every numeric claim in internal docs, dashboards, customer-facing
material, and slide decks.

## Minimum Requirements

- ≥ 3 seeds / runs for any reported mean (≥ 5 preferred).
- Report dispersion: std, or 95% bootstrap CI (preferred for skewed metrics like latency).
- Significance tests for any "better than" claim: paired bootstrap or permutation by default;
  McNemar for paired classification.
- Multiple-comparison correction (Holm / Bonferroni) when comparing many systems.

## Effect Size

Report effect size, not just p-values (Cohen's d, win-rate, or absolute gap with CI).
A statistically significant 0.2-point gap rarely matters; document the threshold that does.

## Power & Sample Size

If the test set is small, report a power analysis or note the minimum detectable effect,
so we don't claim parity when the experiment couldn't have detected the gap.

## Tables & Figures

- Bold-best only when the difference is significant.
- Error bars on every plotted mean.
- Color-blind-safe palette; figure rendered at presentation DPI.
```

#### ethics-and-licensing/README.md

```markdown
# Ethics & Licensing

We follow these standards because they're the right way to handle data and because they
protect the company legally and reputationally — even when results stay internal.

- [Datasheet](./datasheet.md) — Gebru et al. style
- [Licensing & Data Handling](./licensing-and-data-handling.md)
```

#### ethics-and-licensing/datasheet.md

```markdown
# Datasheet for [Dataset Name]

Follows Gebru et al., "Datasheets for Datasets" (2021). Answer every question; "N/A" is
acceptable if justified. Filling this out forces us to surface PII risk, license gaps, and
representativeness problems before they bite.

## Motivation

- For what purpose was the dataset created?
- Who created it and which team / budget funded it?

## Composition

- What do the instances represent?
- How many instances?
- Does the dataset contain all possible instances or is it a sample? If a sample, is it
  representative of customer workloads? How was representativeness validated?
- What data does each instance consist of (raw / processed / features / labels)?
- Is there a label / target associated with each instance?
- Is any information missing from individual instances?
- Are relationships between instances made explicit?
- Are there recommended dev/test splits?
- Are there errors, noise, or redundancies?
- Is the dataset self-contained or does it link to external resources?
- Does the dataset contain confidential customer information?
- Does the dataset contain content that might be offensive, insulting, threatening, or cause
  anxiety to annotators or downstream users?

## Collection Process

- How was the data acquired (directly observable, reported by subjects, inferred, synthetic,
  derived from customer data)?
- What mechanisms / procedures were used to collect the data?
- If a sample, what was the sampling strategy?
- Who was involved in the data collection process (annotators, internal staff, vendors) and
  how were they compensated?
- Over what timeframe was the data collected?
- Were ethical / legal review processes conducted (privacy, IRB-equivalent, customer
  consent)?
- For data derived from customers: what is the consent basis? Can a customer request removal?

## Preprocessing / Cleaning / Labeling

- Was any preprocessing/cleaning/labeling done? Describe.
- Was the "raw" data saved in addition to the cleaned data?
- Is the software used to preprocess/clean/label available?

## Uses

- Has the dataset been used for any tasks already? Internally or externally?
- Internal registry of analyses that depend on it.
- What other tasks could it be used for?
- Tasks for which it should *not* be used.

## Distribution

- Internal access policy (which teams, what auth).
- If shared with vendors (e.g., to let a competitor run their system on the inputs): under
  what NDA, which fields, which splits, labels withheld.
- If externally published (subset or full): see [[hosting-and-versioning]].

## Maintenance

- Owner team and on-call contact.
- How errata / issues are reported and tracked.
- Update cadence and how downstream consumers are notified.
- For data relating to people: retention policy and deletion mechanism.
- Whether older versions remain supported.
```

#### ethics-and-licensing/licensing-and-data-handling.md

```markdown
# Licensing & Data Handling

## Licensing

| Artifact | License | SPDX ID | Internal Use | External Sharing |
|----------|---------|---------|--------------|------------------|
| Code     | …       | …       | …            | …                |
| Data     | …       | …       | …            | …                |
| Model weights / outputs (if released) | … | … | … | … |

- **Compatibility note**: confirm dataset license permits the evaluation use we describe
  and any external sharing we plan.
- **Per-source licenses**: if data is aggregated, list each upstream source's license and
  any attribution requirements.
- **Vendor terms-of-service compliance**: confirm we are allowed to (a) run each competitor
  on our data and (b) publish comparative numbers. Some vendor ToS forbid the latter —
  document this per competitor.

## PII / Sensitive Content

- PII detection method and results.
- Removal / redaction process.
- Residual risk and reporting channel for issues.
- Access controls on the raw vs. redacted versions.

## Broader Impacts (Internal Lens)

- **Intended internal uses**: which decisions this benchmark supports.
- **Foreseeable misuses**: cherry-picked screenshots in sales decks, claims outside scope,
  publishing without permission. Document the guardrail for each.
- **External-claim policy**: who must sign off before a benchmark number leaves the company,
  and what context must accompany it (version, runs, CI).
```

#### distribution/README.md

```markdown
# Distribution

How the benchmark artifacts are stored, versioned, and run — internally and (if applicable)
externally.

- [Hosting & Versioning](./hosting-and-versioning.md)
- [Run & Submission Process](./run-and-submission-process.md)
```

#### distribution/hosting-and-versioning.md

```markdown
# Hosting & Versioning

## Hosting

| Artifact | Primary Host | Backup | Internal URL | External URL (if published) |
|----------|--------------|--------|--------------|------------------------------|
| Code     | GitHub / GitLab | …   | …            | …                            |
| Data     | S3 / GCS / HF private | … | …       | …                            |
| Results dashboard | …   | …      | …            | —                            |

If we publish any artifact externally, prefer an archival host (Zenodo / institutional repo)
so external consumers get a stable DOI.

## Machine-Readable Metadata

- **Croissant** metadata file at `[path]` for interop with HF / Kaggle / TFDS tooling
  (useful even for internal data — gives us a typed schema we can validate against).
- Schema validates against `mlcommons/croissant` reference validator.

## Versioning Policy

- Semantic versioning for code; date-based versioning (`vYYYY.MM`) for data unless
  changes are breaking, in which case bump major.
- A changelog at `[path]` records every dataset/code change with rationale.
- Old versions remain downloadable; published results pin a specific data version + scoring
  script commit, so a number on a slide can always be traced back to exact artifacts.

## Maintenance

- Owner team and on-call contact.
- Triage SLA for issues (broken download, scoring bug, vendor API drift).
- Cadence for re-running competitors whose hosted APIs may have drifted.
```

#### distribution/run-and-submission-process.md

```markdown
# Run & Submission Process

## How a System Gets Evaluated

1. Engineer configures the system (ours or a competitor) following [[evaluation-protocol]].
2. Generates predictions in the required format.
3. Runs the scoring script; results land in the results dashboard with provenance.
4. A second engineer reviews the configuration and re-runs on a sample to confirm.

## Provenance Captured per Run

- System identity, version / API date, configuration hash.
- Data version, scoring script commit.
- Compute used (and $ cost for hosted APIs).
- Seeds, wall-clock, environment digest.
- Operator and date.

Every number in the dashboard, slide deck, or external doc must be traceable to a captured
run.

## Anti-Bias Measures

- Same data version, same scoring script commit, same configuration policy for every system
  in a head-to-head comparison.
- Periodic blind re-runs of competitors to detect API drift.
- Audit: a sample of runs is hand-verified to confirm scoring matches human judgment on
  ambiguous cases.

## Releasing Numbers Externally

- Who approves external publication of a number.
- Required context: benchmark version, number of runs, dispersion, date.
- Vendor ToS check (some vendors forbid published comparisons) — see
  [[licensing-and-data-handling]].
```

#### tasks/README.md

```markdown
# Tasks

- [Active](./active.md) — current experiments and benchmark improvements
- [Backlog](./backlog.md) — proposed tasks, new competitors, refresh schedule
```

#### tasks/active.md

```markdown
# Active Tasks

## Current Milestone

**Target**: [release / customer commitment / quarter goal]

## In Progress

| Task | Owner | Linked Q / Section | Status | Notes |
|------|-------|--------------------|--------|-------|
| _e.g., Run Competitor C at 3 seeds on test_ | … | Q2 / headline table | … | … |

## Blocked / Needs Decision

_None yet._
```

#### tasks/backlog.md

```markdown
# Backlog

## Benchmark Coverage

- _e.g., Add multilingual slice for tasks 1–3._
- _e.g., Add new task covering capability X requested by product._

## New Systems to Add

- _e.g., Competitor D launched, evaluate at next refresh._

## Refresh Schedule

- _e.g., Re-run hosted-API competitors quarterly; re-run our system every release._

## Known Risks

- _e.g., Test set is small for Task 4 — minimum detectable effect is ~3 points; either
  expand or stop publishing fine-grained comparisons there._
```

### 5. Summary

After creating all files, print a summary:

- List all created files.
- Highlight which sections were pre-filled with detected project data (deps, datasets,
  systems, license, CI).
- Call out sections that **must** be completed before any benchmark number is used to
  drive a decision or leave the company:
  - `ethics-and-licensing/datasheet.md`
  - `ethics-and-licensing/licensing-and-data-handling.md` (incl. vendor ToS check for
    each competitor)
  - `reproducibility/reproducibility-checklist.md`
  - `reproducibility/compute-and-environment.md`
  - `baselines/results.md` (≥ 3 runs and significance tests for any comparison)
  - `distribution/hosting-and-versioning.md`
- Suggest adding this to the project's AI assistant prompt:
  `Read .memory-bank/index.md and linked files to understand this benchmark's specification, evaluation protocol, and reproducibility standards before answering.`
