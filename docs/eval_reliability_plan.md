# Plan — reliable Harmix eval via **avg@k** (simple & practical)

**Status:** ✅ implemented — **avg@k only** (maj@k / self-consistency intentionally
omitted). Flag `--samples-per-question K` (default 1). See §"Implemented" below.

**Motivation:** LLM-judge accuracy swings run-to-run on the *same* questions
(nazar 20.0%→13.3%, oleksandr 68.4%→47.4%, nick 60.0%→40.0%). We want a stable,
comparable number and to know when a change is signal vs. noise.

---

## Implemented (avg@k)

Shipped as `--samples-per-question K` (default **1**; `pam_mcp` + raw/harmix path):

- **Generation:** K independent responses per question, **in parallel** via a pool
  of K Claude Code sessions (each own MCP connection, shared memory/key), one
  question at a time with a **hard barrier** (`answer_samples` in
  `baselines/pam_mcp/baseline.py`).
- **Judging:** every one of the K answers is judged (flattened into one concurrent
  pass in `runner._process_sample_harmix`).
- **Metric = avg@k:** per question, `frac_correct` = mean of the K correct flags;
  persona `judge_accuracy` = mean of those, plus `judge_accuracy_std`. Equals the
  old accuracy exactly when K=1.
- **Answer shown:** the single sample whose judge score is **closest to the mean**
  (ties → highest confidence). The K raw answers are **not** stored — only summary
  stats (`n_samples`, `mean_score`, `score_std`, `frac_correct`).
- **Report:** the built-in harmix report reads these fields from Mongo and shows
  `avg@k`, the persona `± std`, and per-question `avg@K · frac correct · mean±std`
  with the closest-to-mean answer.

**maj@k / self-consistency was intentionally NOT implemented** (per instruction:
avg@k everywhere). The optional statistical rigor in §6 (bootstrap/paired CIs) is
also not yet implemented.

---

## 1. What recent top-tier benchmarks actually do (the popular, simple way)

Across current reasoning benchmarks (AIME, GPQA, MATH, etc.) the standard,
simple convention for a stochastic model is **avg@k**: sample **k** answers per
question, score each, and report the **mean**. It is described as reflecting "the
model's expected single-attempt performance" and "a stable estimate." For **small
test sets** (AIME has ~30 questions — like our personas) the community uses a
**larger k, typically 10**; k=5 for bigger sets.

Two companion numbers often appear next to it:

- **maj@k** (a.k.a. cons@k) — majority-vote / consensus accuracy: pick the answer
  the k samples agree on, score that. Measures output *stability*. **This is the
  self-consistency idea — and it's the mode that yields a single answer to show.**
- **pass@k** — did *any* of the k succeed (an upper bound). Useful for
  capability, not for a headline accuracy; we can skip it.

So the practical recipe = **avg@k as the headline, reported with a spread
(± std over the k), and optionally maj@k beside it.** This is exactly your
original idea ("multiple inferences per question, evaluate each, aggregate"); the
aggregation for the *metric* is just the mean.

Sources: [AIME24 multi-sample metrics](https://www.emergentmind.com/topics/aime24-benchmark) ·
[AIME 2025 analysis](https://intuitionlabs.ai/articles/aime-2025-ai-benchmark-explained) ·
[Adding Error Bars to Evals, Miller 2024](https://arxiv.org/abs/2411.00640).

---

## 2. What we build (simple version)

One flag, one default-off behavior change:

- **`--samples-per-question K`** (default **1** → identical to today, no extra cost).
  When used, K≈**10** for our small personas, or **5** to save budget.
- For each question: generate **K answers in parallel**, judge **each in parallel**,
  then a **hard barrier** — do not move to the next question until all K answers are
  received *and* judged. (Your exact execution requirement.)
- **Headline metric = avg@k**: per question, average the K judge scores → a
  per-question score in [0,1]; the persona score is the mean of those. Report the
  **standard deviation across questions** next to it (`68.4% ± 9.1%`). Simple, and it
  is what benchmarks print.
- **Optional `maj@k`** (second number, cheap): the accuracy of the consensus answer
  (see §3). Off by default; enable with `--report-majk`.

That's the whole reliability change most benchmarks ship. Everything else (bootstrap
CIs, paired tests, power analysis) is **optional rigor**, moved to §6 — not needed
for the simple, popular path.

---

## 3. Which answer do we SHOW in the report? (your question)

This is the crux. It depends on the aggregation, and the two cases are different:

**Case A — avg@k (the default, score-averaging).** There is **no single "winning"
answer** — the per-question result is a *fraction*, e.g. `0.6 = 3 of 5 samples
correct`. So the report shows:

- **Headline per question:** the mean score and the split, e.g. **"0.6 — correct in
  3/5 samples."** (Not a single ✓/✗.)
- **One representative answer inline:** pick the sampled answer whose judge score is
  **closest to the per-question mean** (ties → highest judge confidence). This keeps
  the displayed text *consistent with the number* — you're not cherry-picking the
  best or worst draw.
- **Expandable "all K samples":** each of the K answers with its own judge
  score/verdict/latency, so you can see the spread that produced the fraction.

**Case B — maj@k / self-consistency (opt-in).** Here a single answer **is**
well-defined and is what you show: the **consensus answer** — for free-form text we
use **Universal Self-Consistency** (give the judge all K candidates, ask it to pick
the one most consistent with the rest; no embeddings needed). The report shows that
one consensus answer, its ✓/✗, and "agreed by m/K samples."

**Recommendation:** default to **Case A** (avg@k) and display the *closest-to-mean*
representative answer; turn on **maj@k** when you specifically want one clean
consensus answer per question. In short: *averaging gives a score + a representative
sample; majority/consensus gives a single answer.*

---

## 4. Execution & code (parallel + barrier)

- **Session pool in `pam_mcp`.** A `ClaudeCodeSession` is one subprocess with a
  single pipe — it can't take K concurrent sends. So in `prepare_for_sample` open a
  **pool of K sessions** (K `claude` processes) sharing the one MCP key/memory,
  instead of the current single session. New `answer_samples(prompt, K)` fans the
  same prompt to all K via `asyncio.gather` (barrier) and returns K answers.
- **Per-question loop** (`tasks/harmix/pipeline.py` / `runner._process_sample_harmix`):
  ```
  for q in questions:                       # sequential, one question at a time
      answers  = await answer_samples(q, K) # K in parallel   ── barrier
      verdicts = await judge_many(answers)  # K in parallel   ── barrier (judge already concurrent)
      score    = mean(v.score for v in verdicts)      # avg@k
      shown    = closest_to_mean(answers, verdicts)   # representative answer to display
      # optional: consensus = usc_pick(answers); majk = judge(consensus)
  ```
- **Cost:** K× generation + K× judge + K processes per persona. Default K=1 keeps
  today's cost. Log the K multiplier when K>1.

Touch-points: `config.py` (`samples_per_question`, `report_majk`), `mcp_cli.py`
(flags + plumb), `runner.py` (loop, aggregate, qa rows), `tasks/harmix/pipeline.py`,
`baselines/pam_mcp/baseline.py` (session pool + `answer_samples`), the report
generator, `docs/flags.md`, tests.

**Storage (`qa_responses` per question):** `n_samples`, `samples: [{answer,
judge_score, judge_correct, latency, tokens}]`, `mean_score`, `score_std`,
`shown_answer` (closest-to-mean), and if maj@k on: `consensus_answer`, `majk_correct`.
Metric doc gains `judge_accuracy` (= avg@k), `judge_accuracy_std`,
`samples_per_question`, and `majk_accuracy` (optional).

---

## 5. Report changes

- Accuracy bars gain a **± std** whisker (the spread across questions).
- Per-question rows show **"score 0.6 (3/5)"** with the representative answer and an
  expander for all K samples.
- Keep the existing paired old-vs-new layout; add a one-line note when the two runs'
  bars overlap within ± std ("difference within noise").

---

## 6. Optional rigor (only if we want more than the simple norm)

Not required for the popular path; add later if we need defensible significance:

- **Bootstrap 95% CI** over questions (honest at n<30) instead of plain ± std.
- **Paired run-vs-run Δ CI** (compare on identical questions; ~1/3 less variance) —
  the cheap, correct way to claim "run B > run A." [Miller 2024]
- **Min detectable effect** for our n (print it so sub-MDE moves aren't over-read).

---

## 7. The honest caveat

avg@k stabilizes the **within-question** (sampling) noise — real, and what makes the
number reproducible run-to-run. It does **not** shrink the **small-n** noise: with
10–21 questions, one question flipping is still ~5–10 points. The durable fix is
**more questions per persona**. avg@k + ± std is the popular, practical mitigation;
growing the question set is the structural one.

---

## 8. Decision summary

| Choice | Recommendation |
|---|---|
| Metric | **avg@k** (mean of per-question mean judge scores), default K=1, use K≈10 |
| Spread | **± std across questions** (simple); bootstrap CI optional |
| Answer shown | **representative = closest-to-mean sample** (avg@k) |
| Single consensus answer | only under **maj@k / self-consistency** (opt-in) |
| Execution | **K parallel per question + hard barrier**, via a K-session pool |
| Real reliability fix | **more questions** (avg@k can't fix small-n) |
