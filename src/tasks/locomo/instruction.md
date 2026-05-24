# LoCoMo task

Evaluates an LLM's long-context conversational memory by answering questions about multi-session conversations between two people. For [Harmix](https://manager.harmix.ai), LoCoMo is the M1 baseline-capability check before Pam and the dedicated memory competitors join the benchmark in later milestones — if a plain LLM can already answer well on full-context recall, the marginal value of a memory product on this dataset is bounded.

- **Paper:** *Evaluating Very Long-Term Conversational Memory of LLM Agents* (ACL 2024) — https://aclanthology.org/2024.acl-long.747.pdf
- **Source:** https://github.com/snap-research/locomo
- **Dataset assets:** `src/datasets/locomo/` (loader, schemas, data — see its README)

## What this task does

For each sample in `locomo10.json`:

1. Loads the conversation (`speaker_a`, `speaker_b`, `session_{i}` + `session_{i}_date_time`).
2. For each QA pair, builds a single prompt that packs the conversation in reverse-session order until the model's context window is full.
3. Calls the baseline once per question (no batching in M1) and records the prediction, latency, and token usage.
4. Scores predictions with **two metrics** in parallel:
   - **F1** (LoCoMo paper's normalized-token F1, kept for parity with published numbers)
   - **LLM-as-judge** (instructor + pydantic rubric, primary cross-baseline metric)
5. Writes one Mongo document per `(exp_name, sample_id, seed)` to `locomo_results` with the full per-question payload in `qa_responses`.

## Question categories

| ID | Name | Prompt twist | Scoring notes |
|----|------|--------------|---------------|
| 1 | single_hop | none | multi-answer F1 (comma-split both sides) |
| 2 | temporal | "Use DATE of CONVERSATION to answer with an approximate date" | F1 |
| 3 | open_domain | none | F1 against first `;`-separated ground-truth form |
| 4 | multi_hop | none | F1 |
| 5 | adversarial | two-option multiple choice with deterministic seed-based ordering | full credit only when the model declines ("not mentioned"/"no information available") |

The category-5 randomized (a)/(b) ordering is **seeded** (`--seed`) so two runs with the same seed see identical option layouts.

## Run

### Local

```bash
uv run python scripts/run_benchmark.py \
  --dataset locomo \
  --baseline gpt-4-turbo \
  --exp-name locomo_gpt4_smoke \
  --sample-index 0 --max-questions 5
```

### Docker

```bash
docker build -f cluster/Dockerfile -t pam-benchmark:dev .
docker run --rm --env-file secrets.env \
  -v "$(pwd)/outputs:/app/outputs" \
  pam-benchmark:dev \
  scripts/run_benchmark.py \
    --dataset locomo --baseline gpt-4-turbo \
    --exp-name docker_smoke --sample-index 0 --max-questions 5
```

### Cloud Run Jobs

```bash
./cluster/run_job.sh \
  --exp-name locomo_gpt4_full \
  --dataset locomo --baseline gpt-4-turbo
```

Multi-seed (run N times, same `--exp-name`, different `--seed`):

```bash
for s in 42 1337 2024; do
  ./cluster/run_job.sh --exp-name locomo_gpt4_3seed --dataset locomo \
    --baseline gpt-4-turbo --seed "$s"
done
```

## CLI flags (LoCoMo-relevant subset)

| Flag | Default | Notes |
|---|---|---|
| `--dataset` | (required) | `locomo` |
| `--baseline` | (required) | `gpt-4-turbo` (or any LiteLLM model id) |
| `--exp-name` | (required) | groups Mongo records + reports |
| `--seed` | 42 | seeds RNG; passed through to provider when supported |
| `--sample-index` | all | run a single sample by 0-based index |
| `--max-questions` | all | cap questions per sample (useful for smoke tests) |
| `--judge-model` | `gpt-4o` | LLM-judge model id (LiteLLM identifier) |
| `--judge-concurrency` | 8 | max concurrent judge calls |
| `--baseline-kwargs` | `{}` | JSON dict; e.g. `'{"temperature": 0.0, "max_tokens": 1024}'` |
| `--no-mongo` | off | skip Mongo writes (local-only) |
| `--log-format` | `rich` | `json` for Cloud Logging |

## Outputs

- Local: `outputs/<exp-name>/<seed>/{config.yaml, metrics.json}`
- Mongo: collection `locomo_results`, one document per `(exp_name, sample_id, seed)`, with all per-question detail in `qa_responses` (question, expected_answer, model_answer, f1_score, judge_correct, judge_score, judge_reasoning, input_tokens, output_tokens, est_cost_usd, latency_ms).
- Report: `uv run python scripts/generate_report.py --exp-name <name>` → `reports/<name>/report.html`.

## Files

```
src/tasks/locomo/
├── instruction.md     # this file
├── pipeline.py        # run_sample(sample, baseline, ...) — drives one sample
├── prompts.py         # build_prompt(sample, qa, model=..., seed=...) — LoCoMo prompts
└── README.md          # short overview (next to this file)
```
