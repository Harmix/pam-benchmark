# Pam Benchmark — Memory Bank

The internal knowledge base for the benchmark that [Harmix](https://manager.harmix.ai) uses to validate the memory layer inside **Pam** (Proactive AI Manager).

## What is Pam, and why does this benchmark exist?

Pam is Harmix's enterprise AI business assistant. It learns continuously from organizational data — documents, ERP/CRM systems, Linear, Slack, retrospectives — to anticipate problems, automate workflows, and resolve conflicts across disparate tools. Memory is the foundation of every other capability: if Pam can't reliably recall what was said in a Slack thread three months ago, the proactive suggestions on top of that recall fall apart.

This benchmark exists to keep that memory layer honest. It runs Pam and competing memory products (Honcho, Supermemory, mem0, Zep, Claude Code variants, OpenClaw) under identical conditions on memory-oriented public datasets (LoCoMo, BEAM, DRBench, LongMemEval, MEMTRACK, MemoryAgentBench), with the same scoring, the same judge model, and the same seeds — so any number we put in front of a Harmix engineering, product, or customer audience is defensible and reproducible.

## Quick Links

- [Benchmark Overview](./benchmark-overview/README.md) — goals, questions, scope
- [Benchmark Spec](./benchmark-spec/README.md) — tasks, datasets, metrics, protocol
- [Baselines](./baselines/README.md) — systems under test (M1: gpt-4-turbo; M2: Pam)
- [Reproducibility](./reproducibility/README.md) — checklist, environment, statistics
- [Ethics & Licensing](./ethics-and-licensing/README.md) — datasheet, data handling
- [Distribution](./distribution/README.md) — hosting, versioning, run process
- [Tasks](./tasks/README.md) — active work and backlog

## Audience for Results

- **Internal (Harmix):** engineering (regression detection per Pam release), product (capability gaps vs. competitors), leadership (positioning calls).
- **External (gated):** Harmix prospects, customers, analyst conversations. Every external number must clear the sign-off in `ethics-and-licensing/licensing-and-data-handling.md`.

## Current Status

- **Phase**: M1 **complete** — harness validated end-to-end on `gpt-4-turbo` × LoCoMo. M2 (Pam baseline + multi-seed) is the next milestone.
- **Version**: v0.1.0 (tagged `m1`)
- **Last Updated**: 2026-05-23
- **Product page:** <https://manager.harmix.ai>
