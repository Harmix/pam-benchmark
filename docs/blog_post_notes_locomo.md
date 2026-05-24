# Blog Post Notes: Pam Sets New State-of-the-Art on LoCoMo Memory Benchmark

*Notes for the [Harmix](https://manager.harmix.ai) marketing team. Use these as the skeleton for a blog post or for collateral on the product site.*

> **Historical context.** These notes were written under the legacy Harbor-based pipeline. File paths and CLI commands reference that old structure; the underlying narrative (LoCoMo, LLM-as-judge methodology, Pam vs. Mem0 comparison framing) is still useful background for the rewritten harness. Specific paths like `tasks/locomo/environment/task_eval/evaluation.py` should be re-mapped to the new layout (e.g. `src/evals/qa_f1.py`) when this becomes a real blog post.

---

## 1. The LoCoMo Benchmark: The Standard Test for Long-Term AI Memory

The **LoCoMo** (Long-term Conversational Memory) benchmark, published at ACL 2024 by Snap Research (Maharana et al., 2024), has become the go-to evaluation for how well AI systems remember information across extended, multi-session conversations.

**What it tests:** LoCoMo contains 10 long conversations (averaging ~600 dialogue turns and ~26,000 tokens each) between two people discussing daily life, events, and experiences across multiple sessions. After each conversation, approximately 200 questions are asked — testing whether the system can recall specific facts.

**Question categories (4 evaluated, 1 excluded):**
- **Single-hop** — retrieve a single fact from one dialogue turn ("What book did Melanie read?")
- **Multi-hop** — synthesize information scattered across multiple sessions ("What activities did Caroline do with her family?")
- **Temporal** — reason about dates, sequences, and time references ("When did Melanie paint the sunrise?")
- **Open-domain** — infer likely answers based on conversation evidence ("Would Caroline still want counseling if she had no support growing up?")
- **Adversarial** — recognize unanswerable questions (excluded from LLM-as-a-Judge scoring by all systems, as ground truth answers are unavailable)

**Why it matters:** Unlike simple QA benchmarks, LoCoMo tests what real-world AI assistants need most — the ability to maintain coherent knowledge across conversations that span days or weeks, with information scattered across sessions. This is exactly the challenge that any production memory system must solve.

**The evaluation metric:** All systems in this comparison use **LLM-as-a-Judge** (GPT-4o-mini), which provides a binary CORRECT/WRONG judgment for each answer. This metric is more reliable than traditional token-overlap metrics (like F1 or BLEU) because it evaluates semantic correctness — an answer like "2022" and "Last year before May 2023" would both be judged CORRECT even though their token overlap is low.

---

## 2. Why Compare Pam with Mem0?

**Mem0** (Chhikara et al., 2025) is currently the leading open-source memory system for AI agents. Their paper, published in April 2025, reports state-of-the-art results on LoCoMo, outperforming six categories of baselines including RAG approaches, full-context processing, OpenAI's built-in memory, and other memory-augmented systems (MemGPT, MemoryBank, ReadAgent, A-Mem, LangMem, Zep).

**Mem0 claimed SOTA:** 66.88% overall LLM-as-a-Judge accuracy, with a 26% relative improvement over OpenAI's proprietary memory feature.

Comparing Pam against Mem0 on the same benchmark, using the same evaluation protocol, is the most direct way to demonstrate where Pam stands relative to the current best-in-class memory system.

---

## 3. Experimental Settings

All three systems in our comparison were evaluated on the LoCoMo benchmark under the same protocol:

- **Evaluation metric:** LLM-as-a-Judge (GPT-4o-mini) — binary CORRECT/WRONG per question
- **Questions evaluated:** 1,540 non-adversarial questions (adversarial Category 5 is excluded by all systems, consistent with Mem0's methodology)
- **Dataset:** Full LoCoMo dataset (10 conversations)

**What "OpenAI" means on the chart:** This refers to OpenAI's built-in memory feature available in the ChatGPT interface (using gpt-4o-mini). In the Mem0 paper's setup, entire LoCoMo conversations were ingested into single ChatGPT sessions with explicit prompts to generate memories including timestamps and speaker names. These generated memories were then used as complete context for answering questions. Notably, OpenAI's system was given privileged access to *all* memories (not just question-relevant ones), since their API does not support selective memory retrieval. Despite this advantage, OpenAI scored only 52.90%.

**Mem0 setup (from their paper):** Mem0 uses an incremental memory processing pipeline — it extracts salient facts from conversation pairs, consolidates them against existing memories (add/update/delete/noop), and stores them as dense natural-language memory entries. At query time, it retrieves relevant memories for both speakers and uses them as context for answer generation. All LLM operations use GPT-4o-mini.

**Pam setup:** Pam (Proactive AI Manager) uses a local file-first memory architecture with a proprietary Memory Agent. Instead of storing memories in a database accessed through API calls, Pam processes conversations into structured local files organized by topic. At query time, the agent uses native file operations (search, read) to find relevant information in its file-based memory — aligning with the LLM's intrinsic strengths in reading files and executing commands.

---

## 4. Results

| System | LLM-as-a-Judge Accuracy | Correct / Total |
|--------|------------------------|-----------------|
| OpenAI (ChatGPT memory) | 52.90% | — |
| Mem0 (previous SOTA) | 66.88% | — |
| **Pam (Ours)** | **74.35%** | **1,145 / 1,540** |

**Key findings:**
- Pam achieves **74.35%** overall LLM-as-a-Judge accuracy, establishing a new state-of-the-art on LoCoMo
- This represents a **+7.47 absolute point improvement** over Mem0 (66.88%), the previous best result
- Pam outperforms OpenAI's built-in memory by **+21.45 absolute points** (a 40.5% relative improvement)
- Pam outperforms Mem0 by **11.2% relative improvement**

**Per-category breakdown (Pam):**
- Multi-hop: 80.1% (678/841) — strongest category, showing Pam's ability to synthesize scattered information
- Temporal: 72.9% (233/321) — strong temporal reasoning from structured date/time in file memory
- Single-hop: 69.9% (197/282) — reliable single-fact retrieval
- Open-domain: 37.2% (37/96) — hardest category across all systems, requires inference beyond stated facts

---

## 5. Why Pam Is Better: The File-First Architecture Advantage

The key insight behind Pam's superior performance lies in a fundamental architectural difference: **how the agent interfaces with its memory.**

### The problem with memory-as-a-database

Systems like Mem0, OpenAI, and Zep treat memory as a database — facts are stored as entries, and retrieval happens through semantic search queries. This introduces several bottlenecks:

1. **Abstraction overhead:** The agent must translate its reasoning into database queries, adding a cognitive layer between "thinking" and "remembering"
2. **Lossy compression:** Converting rich conversation context into short memory entries inevitably loses nuance, relationships, and structure
3. **Retrieval fragility:** Semantic search may miss relevant memories if the query doesn't closely match the stored representation

### Pam's file-first approach

Pam takes a fundamentally different approach. Instead of abstracting memory behind an API, Pam's Memory Agent processes conversations into **structured local files** organized by topic, person, and timeline — much like how a human might organize notes in folders.

This design gives Pam three distinct advantages:

1. **Native tooling alignment:** LLMs are exceptionally good at reading files and navigating directory structures — these are core capabilities from training data. By storing memory as files, Pam leverages the LLM's strongest modality rather than forcing it through an unfamiliar API layer.

2. **Richer context preservation:** File-based memory retains more structure and context than flat database entries. Related facts stay together in organized documents, preserving the relationships between pieces of information that database-style memory systems discard.

3. **Reduced cognitive load:** As demonstrated in our previous research ("The Architecture of Recall"), switching from MCP-based memory to file-first architecture improved accuracy from 41.3% to 92.4% on cross-application tasks — a 51.1% improvement. The simpler the memory interface, the more reasoning capacity the agent can devote to actually answering questions.

### The broader lesson

The industry is focused on larger context windows and more sophisticated retrieval mechanisms. Our results suggest that **the interface between the agent and its memory matters more than the sophistication of the memory system itself.** By aligning memory architecture with how LLMs naturally process information — reading files, not querying databases — Pam achieves state-of-the-art results with a fundamentally simpler design.

---

## Suggested assets to include

- The performance comparison bar chart (docs/pam_performance_chart.html)
- Per-category breakdown table from the Pam evaluation report
- Link to the LoCoMo benchmark paper (Maharana et al., ACL 2024)
- Link to the Mem0 paper (Chhikara et al., 2025)
- Link to the previous Pam blog post ("The Architecture of Recall")
