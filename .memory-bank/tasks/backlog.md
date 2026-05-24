# Backlog

(Mirror of `docs/benchmark_rewrite_plan.md` §14. Kept here too so the memory bank is self-contained.)

## M2 — PAM baseline + multi-seed

- Port PAM off Harbor onto the new harness (baselines/pam/ subpackage).
- Run ≥ 3 seeds; add bootstrap CIs and paired bootstrap tests to the report.
- HTML report polish: error bars, win-rate matrix.
- Compute/cost dashboard.

## M3 — BEAM + DRBench

- Per stated priority. Each is a new `datasets/<name>/` + `tasks/<name>/`.

## M4 — Competitor baselines

- Honcho, Supermemory, mem0, Zep. Reuse their existing metrics where they exist; otherwise our `evals/`.
- Add per-vendor system cards + vendor-ToS rows in [[licensing-and-data-handling]].

## M5 — Claude Code variants

- Claude Code + Memory.md
- Claude Code + Obsidian
- OpenClaw + .md

## M6 — Retrieval baselines

- rank-bm25 / sentence-transformers + faiss-cpu for tasks that support a retrieval setting.
- Adds Python 3.13 re-evaluation (torch + faiss wheels).

## M7 — Remaining datasets

- LongMemEval, MEMTRACK, MemoryAgentBench.

## Cross-cutting

- sha256 verification in `scripts/download_data.py` (TODO before M2).
- CHANGELOG.md (start when M2 lands).
- Contamination audit for LoCoMo against a Common Crawl sample.
- Token-throughput dashboard (when we have enough baselines to compare cost).
