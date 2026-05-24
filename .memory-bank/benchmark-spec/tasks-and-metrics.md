# Tasks & Metrics

## Tasks

### Task 1: LoCoMo question-answering (M1)

- **Input format:** one LoCoMo sample = `(speaker_a, speaker_b, multi-session conversation, list of QA pairs with ground truth)`.
- **Output format:** one short-phrase answer per question, plus token usage and latency.
- **Task definition:** for each QA, build a single prompt packing as much of the conversation (newest sessions first, reversed turns) as fits in the baseline's context window, then ask the model to answer in a short phrase.
- **Why:** the baseline-capability check before Pam joins the benchmark in M2 — confirms F1 parity with the LoCoMo paper and exercises every part of the harness on real data.

## Metrics

| Metric | Range | ↑/↓ | Primary? | Definition |
|---|---|---|---|---|
| `judge_accuracy` | [0,1] | ↑ | **yes** (cross-baseline) | mean over questions of `judge_correct` (LLM judge bool) |
| `overall_accuracy` (F1) | [0,1] | ↑ | yes (paper parity) | LoCoMo-style normalized-token F1, category-dispatched |
| `category_<name>_accuracy` (F1) | [0,1] | ↑ | breakdown | per-category mean F1 |
| `category_<name>_llm_judge_accuracy` | [0,1] | ↑ | breakdown | per-category judge accuracy |
| `total_cost_usd` | ≥ 0 | ↓ | yes | sum of per-question LiteLLM cost estimate |
| `avg_latency_ms`, `p50_latency_ms`, `p95_latency_ms` | ≥ 0 | ↓ | yes | wall-clock per baseline call |

### Aggregation

- Per-question metrics are aggregated per sample and stored as fields on the Mongo doc (`overall_accuracy`, `judge_accuracy`, etc.).
- Per-dataset headline = weighted mean across samples weighted by question count.
- Per-category aggregation re-derives from `qa_responses` at report time (so adding categories doesn't require re-running).

### Known limitations

- **F1** is normalization-sensitive; equivalent phrasing can score < 1. That's why F1 is paper-parity only.
- **LLM-judge** has a small false-positive rate on hedged answers; mitigated by an explicit "no partial credit for hedges" instruction in the rubric.
- **Token counts** are provider-reported and may not include hidden system tokens.
- **Cost estimates** come from LiteLLM's pricing table; for Harmix's enterprise contracts (custom OpenAI/Anthropic pricing) the estimate will be off — treat as a rough comparator, not an invoice.
