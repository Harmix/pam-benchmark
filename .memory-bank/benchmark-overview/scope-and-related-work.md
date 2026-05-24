# Scope & Related Work

## What our benchmark adds (beyond public benchmarks)

1. **Uniform harness across competing memory products.** Same data, same scoring script commit, same `--exp-name` for every system in a head-to-head.
2. **Two metrics in parallel.** LoCoMo's F1 (paper parity) **and** an LLM-as-a-judge rubric (cross-baseline primary metric) reported on every QA.
3. **Cost + latency alongside quality.** Per-question token usage, USD estimate, and p50/p95 latency captured on every run.
4. **MongoDB-first storage with full per-question payloads.** Every question's prompt, prediction, judge verdict, and reasoning live in `qa_responses` — the report renders detail without re-running.
5. **Cloud Run-native execution.** One container image deploys both locally and on GCP for fan-out across configurations.

## Related Public Benchmarks

| Benchmark | Year | Task / Domain | Why It Doesn't Cover Our Need | Reference |
|---|---|---|---|---|
| LoCoMo | 2024 | Multi-session conversational recall | Covered (M1) — see [[datasheet]] | https://aclanthology.org/2024.acl-long.747.pdf |
| LongMemEval | 2024 | Long-conversation memory eval | Slot reserved (M7) | https://arxiv.org/abs/2410.10813 |
| MEMTRACK | n/a | Memory tracking over Linear/Slack events | Slot reserved (M2+) | internal |
| BEAM | 2024 | Conflict-resolution episodic memory | M3 priority | upstream |
| DRBench | n/a | Enterprise event-history memory | M3 priority | upstream |
| MemoryAgentBench | 2024 | Memory-agent capability suite | M7 | upstream |

## Positioning Statement

Unlike running competitors via each vendor's own demo notebook, PAM Benchmark gives us a single Mongo collection per dataset whose rows are directly comparable across vendors, dated for vendor-API drift, and tagged with provenance (`git_commit`, `image_digest`, `uv_lock_hash`) so any number on a slide can be traced back to exact artifacts.
