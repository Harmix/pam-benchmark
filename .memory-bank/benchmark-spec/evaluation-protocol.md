# Evaluation Protocol

## Allowed / Disallowed Resources

- **Allowed at inference:** the conversation passed in the prompt; no external retrieval in M1 (RAG slated for M6).
- **Disallowed:** the test labels; running the baseline with knowledge of the ground truth in any form; ensembling across runs.
- **Configuration rules:** baseline `temperature=0.0`, `max_tokens=1024` by default. Each baseline's full kwargs are stored in the Mongo doc (`baseline_kwargs`).

## Submission Format

- The runner writes one Mongo doc per `(exp_name, sample_id, seed)` to `<dataset>_results` (`locomo_results` for LoCoMo).
- Full schema in `docs/benchmark_rewrite_plan.md` §9.1.
- Each doc carries every per-question record in the `qa_responses` array (question, expected_answer, model_answer, F1, judge verdict + reasoning, tokens, latency).

## Scoring

- Reference implementation: `src/evals/qa_f1.py` (F1) and `src/evals/llm_judge.py` (LLM-judge).
- F1 is deterministic. LLM-judge uses `temperature=0.0` and an `instructor`-typed rubric; runs are reproducible up to provider non-determinism.

## Tracks

| Track | Constraints | When to use |
|---|---|---|
| out_of_the_box (default) | Default settings, no per-task tuning | "What does a customer get on day one?" |
| tuned | Per-task prompt/config tuning allowed | "What is each system capable of with effort?" — not yet exercised in M1 |

## Comparison Fairness Rules

- Same data version, same scoring-script commit, same `--exp-name` for every system in a head-to-head.
- Same `--judge-model` per comparison; record `judge_model` in Mongo and the report.
- Document any per-system deviation in the Mongo doc's `baseline_kwargs` and call it out in the report's per-sample table.

## Anti-Gaming Measures

- Test labels never sent to baselines.
- Periodic blind re-runs of hosted-API competitors to detect drift.
- External-publication sign-off per [[licensing-and-data-handling]].
