# PAM Benchmark — Memory Bank

A persistent knowledge base for the PAM Benchmark — the framework we use to compare our memory solution (PAM) against competing memory products on memory-oriented datasets.

## Quick Links

- [Benchmark Overview](./benchmark-overview/README.md) — goals, questions, scope
- [Benchmark Spec](./benchmark-spec/README.md) — tasks, datasets, metrics, protocol
- [Baselines](./baselines/README.md) — systems under test (M1: gpt-4-turbo)
- [Reproducibility](./reproducibility/README.md) — checklist, environment, statistics
- [Ethics & Licensing](./ethics-and-licensing/README.md) — datasheet, data handling
- [Distribution](./distribution/README.md) — hosting, versioning, run process
- [Tasks](./tasks/README.md) — active work and backlog

## Benchmark Summary

PAM Benchmark measures how well memory-augmented LLM systems can answer questions about long, multi-session conversations and other memory-stressing inputs. The decisions it supports: which memory product to ship as PAM's backbone, when PAM regresses, and what to publish externally about PAM vs. competitors. M1 is a vertical slice — `gpt-4-turbo` baseline on the LoCoMo dataset — proving the new (post-Harbor) architecture.

## Audience for Results

- **Internal**: engineering (regression detection per release), product (capability gaps vs. competitors), leadership (positioning).
- **External (gated)**: customer-facing claims about PAM vs. specific competitors. Every external number must clear the sign-off in `ethics-and-licensing/licensing-and-data-handling.md`.

## Current Status

- **Phase**: M1 implementation in progress; first end-to-end run pending.
- **Version**: v0.1.0
- **Last Updated**: 2026-05-23
