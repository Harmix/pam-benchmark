# Baselines

Each system under test (our solution + each competitor) is implemented as a `Baseline`
subclass conforming to the protocol in `baselines/base.py`. M1 ships a single concrete
baseline, `LiteLLMBaseline`, which routes any LiteLLM-supported model name (e.g.
`gpt-4-turbo`, `gpt-4o`, `claude-3-5-sonnet`) through a unified async interface.

## Adding a new baseline

1. Create a subpackage under `src/baselines/<name>/` (or a single module for trivial baselines).
2. Implement the `Baseline` protocol from `baselines/base.py`:
   - `name`, `track`
   - `async setup(seed)`, `async teardown()`
   - `async answer(prompt, max_tokens) -> BaselineResponse`
3. Register the baseline in `src/registry.py` so it's resolvable from `--baseline <name>`.
4. Add a system card to `.memory-bank/baselines/system-cards.md`.

Future M2+ baselines include PAM (our solution), Honcho, Supermemory, mem0, Zep, Claude
Code with Memory.md, Claude Code + Obsidian, OpenClaw + .md.
