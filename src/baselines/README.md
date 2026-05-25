# Baselines

Each system under test — Harmix's [Pam](https://manager.harmix.ai) and each memory competitor — is implemented as a `Baseline` subclass conforming to the protocol in `baselines/base.py`.

Shipped:

- **`LiteLLMBaseline`** — routes any LiteLLM-supported model name (e.g. `gpt-4-turbo`, `gpt-4o`, `claude-…`) through a unified async interface. Single-call per question; harness packs the full conversation into every prompt.
- **`PamBaseline`** (`src/baselines/pam/`) — the M2 system under test. External memory: harness uploads the conversation once, Pam builds a memory, then questions are answered in batches over SSE. See `src/baselines/pam/README.md`.

## Adding a new baseline

1. Create a subpackage under `src/baselines/<name>/` (or a single module for trivial baselines).
2. Implement the `Baseline` protocol from `baselines/base.py`. The common case (single-call, harness-packed prompt) only needs `setup`, `answer`, `teardown`. External-memory baselines that want per-sample lifecycle hooks override `prepare_for_sample` / `cleanup_sample` / `answer_batch` (defaults live in `BaselineBase`) and set `external_memory = True` + `batch_size = N`.
3. Register the baseline in `src/registry.py` so it's resolvable from `--baseline <name>`.
4. Add a system card to `.memory-bank/baselines/system-cards.md`.

Milestone roadmap:

- **M2** — Pam (Harmix's Proactive AI Manager — <https://manager.harmix.ai>). The system under test the rest of the cards are measured against. **Shipped.**
- **M4** — Dedicated memory competitors: Honcho, Supermemory, mem0, Zep.
- **M5** — Claude Code + Memory.md, Claude Code + Obsidian, OpenClaw + .md.
