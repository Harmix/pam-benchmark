# Goals & Questions

## Q1: Is the new architecture able to reproduce the LoCoMo F1 baseline?

- **Question:** Does `gpt-4-turbo` via `LiteLLMBaseline` on the new harness produce LoCoMo F1 numbers within ±1 pp of the legacy Harbor-based pipeline on the same `locomo10.json`?
- **Why it matters:** validates the prompt port and the F1 implementation. If parity holds, future regressions can be attributed to PAM/competitor differences rather than harness drift.
- **Metric:** weighted F1 across all 10 samples × ~200 questions.
- **Threshold:** within ±1 pp of the previously recorded number for `gpt-4-turbo` on LoCoMo.
- **Status:** pending (will be answered by the first full M1 run — see [[tasks/active]]).

## Q2: How well does our LLM-as-a-judge agree with F1?

- **Question:** When the judge marks an answer correct, does F1 ≥ 0.5 in the majority of cases (and vice versa)?
- **Why it matters:** if agreement is low, we need to investigate the judge prompt and rubric before publishing judge-based numbers.
- **Metric:** confusion matrix (judge_correct × (F1 ≥ 0.5)).
- **Status:** to be checked from M1 results.

## Non-Questions

- This benchmark does NOT measure raw vector-DB latency or vector-recall@k. Use the retrieval-baselines milestone (M6) for that.
- It does NOT measure PAM's planning loop on dynamic tools — only its memory recall.
- It does NOT establish ground truth for new conversations; only existing labeled benchmarks are in scope.
