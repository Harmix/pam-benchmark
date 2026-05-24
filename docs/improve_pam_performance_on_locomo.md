# Pam Performance Improvement Suggestions

> **Historical context.** Error-pattern analysis for [Harmix](https://manager.harmix.ai)'s Pam (Proactive AI Manager) on LoCoMo, written under the legacy Harbor-based pipeline. File paths and metric definitions reference that old structure (e.g. `tasks/locomo/environment/task_eval/evaluation.py`); the new harness lives at `src/evals/qa_f1.py` and `src/evals/llm_judge.py`. The error patterns (adversarial hallucination, token-F1 vs semantic-correctness divergence) still apply and should drive the M2 Pam-integration work.

## Current Metrics (5 samples, 999 questions, Overall F1: 43.3%)

- **Temporal (Cat 2): 68.0%** (178 questions) -- best category
- **Multi-hop (Cat 4): 56.9%** (416 questions)
- **Single-hop (Cat 1): 44.0%** (138 questions)
- **Open-domain (Cat 3): 29.7%** (47 questions)
- **Adversarial (Cat 5): 0.2%** (220 questions) -- catastrophically bad

## Root Cause Analysis by Error Pattern

### Pattern A: Adversarial Hallucination (220 questions, ~0% accuracy)

Category 5 questions are designed so the correct answer is **empty** -- the fact was never mentioned. The eval at [evaluation.py](tasks/locomo/environment/task_eval/evaluation.py) lines 220-224 scores 1.0 only if the response contains `"not mentioned"` or `"no information available"`. Pam confidently fabricates answers instead:

- Q: "What does Melanie's necklace symbolize?" Expected: `""` Pam: `"Love, faith, and strength"`
- Q: "What country is Melanie's grandma from?" Expected: `""` Pam: `"Sweden"`
- Q: "What was grandpa's gift to Caroline?" Expected: `""` Pam: `"Hand-painted bowl from a friend"`

**Root cause**: Pam has zero awareness of adversarial questions. Unlike gpt4-turbo, which formats cat 5 as multiple-choice (`"(a) adversarial_answer (b) Not mentioned"`), Pam receives the raw question with no signal that it might be a trap.

### Pattern B: Semantically Correct but Token-F1 Penalized

Many answers are correct but scored poorly due to pure token-overlap F1:

- Q: "When did Melanie paint a sunrise?" Expected: `"2022"` Pam: `"Last year before May 2023 (2022)"` -- F1: 0.286
- Q: "How many times to beach?" Expected: `"2"` Pam: `"2 times (beach camping in July...)"` -- F1: 0.154
- Q: "Career path?" Expected: `"counseling or mental health for Transgender people"` Pam: `"Counseling/mental health"` -- F1: 0.222

### Pattern C: Over-generation / Hallucinated List Items

Pam lists too many items, many fabricated:

- Q: "LGBTQ events?" Expected: `"Pride parade, school speech, support group"` (3 items) Pam: `"Pride parades, transgender conferences, LGBTQ+ counseling workshops, support groups, poetry readings, LGBTQ art shows, youth center volunteering"` (7 items)
- Q: "Activities with family?" Expected: 6 items Pam: 9 items including fabricated ones ("road trip to Grand Canyon")

### Pattern D: Refusal to Reason on Open-domain Questions

Pam says "Not mentioned" for questions requiring inference:

- Q: "Would Caroline still want counseling if no support growing up?" Expected: `"Likely no"` Pam: `"Not mentioned"`
- Q: "Would Caroline likely have Dr. Seuss books?" Expected: `"Yes, she collects classic children's books"` Pam: `"Not mentioned"`

**Root cause**: The current prompt at [pam_answer.sh](tasks/locomo/environment/pam_answer.sh) line 97 says `"If the information is not available, say 'Not mentioned in the conversation'"` which makes Pam default to refusal for inference questions.

### Pattern E: Wrong Fact Retrieval

Pam retrieves incorrect facts from its memory:

- Q: "Books Melanie read?" Expected: `"Nothing is Impossible, Charlotte's Web"` Pam: `"Becoming Nicole by Amy Ellis Nutt"` (confusing speakers or sessions)

---

## Suggested Improvements (Ranked by Expected Impact)

### S1: Fix Adversarial (Cat 5) Handling -- CRITICAL

**Expected impact**: 0.2% -> ~50%+ on adversarial (lifts overall by ~10+ points)

**Approach**: Pass `category` and `adversarial_answer` to Pam's answering phase. In [pam_answer.sh](tasks/locomo/environment/pam_answer.sh), when building the questions list (lines 64-78), append category info. For category 5 questions, format as multiple-choice like gpt4-turbo does in [gpt_utils.py](tasks/locomo/environment/task_eval/gpt_utils.py) lines 246-264:

```
Q153: What did Caroline realize after her charity race?
  Select the correct answer: (a) self-care is important (b) Not mentioned in the conversation
```

This requires:

1. Including `category` and `adversarial_answer` in `questions.json` (update [pam_utils.py](tasks/locomo/environment/pam_utils.py) `extract_questions()`)
2. Modifying the batch question-building Python in `pam_answer.sh` to format cat 5 as multiple-choice
3. Adding answer-extraction logic to map (a)/(b) back to the selected text

### S2: Add LLM-as-a-Judge Evaluation -- HIGH IMPACT

**Expected impact**: Reveals true accuracy is likely 5-15 points higher than token F1 shows

**Approach**: Adapt the existing implementation from [agents/mem0/metrics/llm_judge.py](agents/mem0/metrics/llm_judge.py) into Pam's evaluation pipeline. The mem0 judge:

- Uses `gpt-4o-mini` with a structured prompt
- Returns CORRECT/WRONG in JSON
- Is generous: "as long as it touches on the same topic"
- Handles date format differences

Add to [pam_evaluate.py](tasks/locomo/environment/pam_evaluate.py) as a secondary metric alongside F1, and expose it in [generate_report.py](tasks/locomo/generate_report.py). Skip cat 5 in LLM judge (use existing binary check). Store both `f1_score` and `llm_judge_score` per question.

### S3: Reduce Verbosity in Answering Prompt -- MEDIUM IMPACT

**Expected impact**: +3-5 points on single-hop and temporal

Update the answering prompt in [pam_answer.sh](tasks/locomo/environment/pam_answer.sh) lines 86-107:

- Change "Be concise" to explicit word limits: "Answer in 1-5 words. Never add explanations, qualifiers, or parenthetical notes."
- For list questions: "List ONLY items explicitly stated in the conversation. Do not add related or inferred items."
- Add few-shot examples showing good concise vs bad verbose answers

### S4: Fix Open-domain (Cat 3) Reasoning -- MEDIUM IMPACT

**Expected impact**: 29.7% -> ~40-50% on open-domain

The prompt currently conflates "not stated" with "requires inference." Update [pam_answer.sh](tasks/locomo/environment/pam_answer.sh) to add:

```
For questions that ask "Would X..." or "Is X likely to...", provide your
best reasoned answer based on conversation evidence. Say "Likely yes"
or "Likely no" with a brief reason. Only say "Not mentioned" when the
topic was NEVER discussed at all.
```

### S5: Reduce Hallucination in Memory Processing -- MEDIUM IMPACT

**Expected impact**: +2-4 points on single-hop

Update the processing prompt in [pam_process.sh](tasks/locomo/environment/pam_process.sh) to add stronger anti-hallucination instructions:

```
CRITICAL: Record ONLY facts that are EXPLICITLY stated in the conversation
text. Do NOT infer, expand, or generalize. If a speaker mentions "pottery",
record "pottery" -- do NOT add "pottery workshop" or "ceramics class"
unless those exact words appear.
```

### S6: Improve Temporal Precision -- LOWER IMPACT

**Expected impact**: +1-3 points on temporal (already 68%)

Add temporal reasoning instructions to answering prompt (similar to mem0's approach in [prompts.py](agents/mem0/prompts.py) lines 77-82):

```
For time questions, calculate specific dates from session timestamps.
Convert relative references ("last week", "two months ago") to actual
dates. Example: if Session 5 is dated "15 July 2023" and mentions
"last Friday", answer "The Friday before 15 July 2023".
```
