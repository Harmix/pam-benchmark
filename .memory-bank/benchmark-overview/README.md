# Benchmark Overview

## What is Pam Benchmark?

A unified evaluation harness that [Harmix](https://manager.harmix.ai) uses to compare its memory layer against competing memory products on memory-oriented datasets.

- **Systems under test (M1+):** `gpt-4-turbo` (baseline-of-baselines); Pam (M2); Honcho, Supermemory, mem0, Zep (M4); Claude Code + Memory.md / Obsidian, OpenClaw + .md (M5).
- **Datasets (M1+):** LoCoMo (M1); BEAM, DRBench (M3); LongMemEval, MEMTRACK, MemoryAgentBench (M7).
- **Metrics:** LLM-as-a-judge with a typed pydantic rubric (primary, cross-baseline) and LoCoMo's normalized-token F1 (secondary, paper parity), reported alongside cost (USD), input/output tokens, and p50/p95 latency on every question.

## Why this benchmark exists

Pam ([manager.harmix.ai](https://manager.harmix.ai)) is Harmix's enterprise AI business assistant — it learns from organizational data (ERP/CRM systems, documents, Linear, Slack, retrospectives) to anticipate problems, automate workflows, and resolve conflicts across tools. The entire value proposition rests on long-horizon recall: every proactive suggestion Pam makes is grounded in what it remembered from days, weeks, or quarters ago.

Pam has its own independent memory layer, built in-house. The other memory products in this benchmark (Honcho, Supermemory, mem0, Zep, Claude Code variants, OpenClaw) are **direct competitors**, not candidate backbones — we don't run this benchmark to decide which product to adopt; we run it to prove Pam's memory layer holds up against them.

That goal supports four recurring Harmix decisions:

1. **Competitive positioning.** Where does Pam's memory layer rank against each dedicated memory competitor, on which workloads do we have an edge, and where do we have gaps to close?
2. **Regression detection.** Does this Pam release recall organizational facts at least as accurately as the previous one?
3. **Configuration tuning.** Inside Pam, which model + retrieval config performs best on the data shapes our enterprise customers actually generate?
4. **Defensible external claims.** When we tell a prospect "Pam is N% better than competitor Y on workload Z," can we ship the experiment log to back it up?

Public memory benchmarks alone aren't enough because: (a) several are saturating for top models, (b) they don't cover Harmix-shaped workloads (multi-tool coordination, ERP-grounded retrospectives, long Slack/Linear histories), and (c) running competitors uniformly on the same data with the same scoring requires harness work that public datasets don't provide.

## Scope

- **In scope (M1):** LoCoMo dataset, `gpt-4-turbo` baseline, F1 + LLM-judge metrics, MongoDB result store.
- **In scope (M2+):** Pam baseline, ≥3 seeds with stats, BEAM, DRBench, competitor baselines (Honcho/Supermemory/mem0/Zep), Claude Code + Memory.md, Claude Code + Obsidian, OpenClaw + .md, retrieval baselines, LongMemEval/MEMTRACK/MemoryAgentBench.
- **Out of scope:** training/fine-tuning competitors on our test data; latency benchmarks of vector DBs alone; anything that conflicts with a competitor's terms of service regarding published comparisons.

## Intended Use

- Internal (Harmix): engineering for regression detection, product for capability-gap analysis, leadership for positioning calls.
- Misuse to avoid: cherry-picking a single sample for a slide; single-seed claims; comparing numbers across different benchmark versions; quoting LoCoMo F1 outside its paper-defined scope.

## Success Criteria for the Benchmark Itself

- A Harmix engineer who didn't build it can reproduce a published number from `cluster/deploy.sh` + the recorded image digest + the same `--exp-name`/`--seed`.
- Adding a new dataset doesn't require editing any other dataset's or task's code (per-task independence).
- Differences flagged as "significant" survive a second independent run.
- Vendor-ToS compliance per `ethics-and-licensing/licensing-and-data-handling.md` blocks any externally published number that would violate it.
