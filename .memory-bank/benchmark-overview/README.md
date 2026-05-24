# Benchmark Overview

## What is PAM Benchmark?

A unified harness for evaluating memory-augmented LLM systems on memory-oriented datasets (M1: LoCoMo; M2+: BEAM, DRBench, LongMemEval, MEMTRACK, MemoryAgentBench). Each system is a `Baseline`; each dataset has a `Task` pipeline; scoring uses shared `evals/` modules — most importantly, **LLM-as-a-judge** (primary) and **F1** (secondary, for paper parity).

## Why this benchmark exists

It supports four recurring internal decisions:

1. **Backbone selection.** Which memory product (Honcho, Supermemory, mem0, Zep, …) should PAM build on for which workload?
2. **Regression detection.** Does this PAM release regress on capability X compared to the previous release?
3. **Configuration tuning.** Which model + retrieval config inside PAM performs best on customer-shaped workloads?
4. **Defensible external claims.** Can we publicly say "PAM is N% better than competitor Y on task Z" with multi-seed CIs and survives vendor-ToS review?

Public memory benchmarks alone aren't enough because: (a) several are saturating for top models, (b) they don't cover our customer workloads (enterprise event histories, structured tools), and (c) running competitors uniformly requires harness work that public datasets don't provide.

## Scope

- **In scope (M1):** LoCoMo dataset, `gpt-4-turbo` baseline, F1 + LLM-judge metrics, MongoDB result store.
- **In scope (M2+):** PAM baseline, ≥3 seeds with stats, BEAM, DRBench, competitor baselines (Honcho/Supermemory/mem0/Zep), Claude Code + Memory.md, Claude Code + Obsidian, OpenClaw + .md, retrieval baselines, LongMemEval/MEMTRACK/MemoryAgentBench.
- **Out of scope:** training/fine-tuning competitors on our test data, latency benchmarks of vector DBs alone, anything that conflicts with a competitor's ToS regarding published comparisons.

## Intended Use

- Internal: engineering for regression detection, product for capability gap analysis, leadership for positioning calls.
- Misuse to avoid: cherry-picking a single sample for a slide; single-seed claims; comparing numbers across different benchmark versions; quoting LoCoMo F1 outside its paper-defined scope.

## Success Criteria for the Benchmark Itself

- An engineer who didn't build it can reproduce a published number from `cluster/deploy.sh` + the recorded image digest + the same `--exp-name`/`--seed`.
- Adding a new dataset doesn't require editing any other dataset's or task's code (per-task independence).
- Differences flagged as "significant" survive a second independent run.
- Vendor-ToS compliance per `ethics-and-licensing/licensing-and-data-handling.md` blocks any externally published number that would violate them.
