# `pam_mcp` baseline — implementation plan

## Goal

Add a new baseline, **`pam_mcp`**, to the MCP-on-harness experiment
(`scripts/run_mcp_benchmark.py`). It builds Pam's server-side memory exactly like
the existing `pam` baseline, but answers questions through an **agentic harness
(Claude Code) using the PAM Memory MCP tool** instead of Pam's chat endpoint.

Scope for this iteration:

- **LoCoMo only** (the only dataset wired into the registry today).
- Harness: **`claude-code`** (the only harness today).
- Reuse all existing machinery: dataset loader, LoCoMo task pipeline, numbered
  Q/A batch protocol, F1 + LLM judge scoring, Mongo (`locomo_mcp_results`),
  reporting.

This document is a plan only — no code is written yet.

---

## Why a new baseline class (not a backend)

`pam_mcp` is a **hybrid** of the two baselines we already have:

| Phase | `pam` (`run_benchmark.py`) | `memory_md_mcp` (`run_mcp_benchmark.py`) | **`pam_mcp` (new)** |
|---|---|---|---|
| Memory build | Pam API: `process-generic-files` + poll | Harness writes local `.md` notes | **Pam API (same as `pam`)** |
| Answering | Pam `messages/stream` SSE | Harness + native file tools | **Harness + PAM Memory MCP** |
| Memory location | Server-side, per Pam user | Local `outputs/.../memory/` | **Server-side, per Pam user** |

Because memory is built **server-side via the Pam API** (not by the harness
writing local files), it does **not** fit `McpHarnessBaseline.prepare_for_sample`
(which calls `harness.run(ingest_prompt(...))`). And because answering goes
through a **harness + MCP** (not Pam's chat endpoint), it does not fit
`PamBaseline.answer_batch`.

**Decision:** introduce a dedicated `PamMcpBaseline(BaselineBase)` that
**composes** the existing `PamClient` (account + memory lifecycle) with the
existing `ClaudeCodeHarness` (answering). It reuses both classes as-is — only a
small new client method (`rotate_developer_key`) and a new prompts module are
added.

---

## End-to-end flow (per LoCoMo sample)

Mirrors `PamBaseline`'s lifecycle, swapping only the answer phase:

1. **`setup(seed)`** — admin sign-in with `PAM_API_USER` / `PAM_API_PASSWORD`
   (`PamClient.login`), and `harness.setup()` (resolves Vertex auth).
2. **`prepare_for_sample(sample)`**
   1. **Create a per-conversation account** — `PamClient.create_account` (same
      endpoint as `pam`: `POST /v1/admin/create-account`). This sets
      `client.access_token` to the **new user's** token and `client.user_id`.
   2. **Upload + build memory** — `PamClient.process_generic_files(serialize_sample(sample))`
      → `run_ids`, then `PamClient.wait_for_memory(run_ids)` (identical polling
      logic to `pam`, reused unchanged).
   3. **Mint a Memory MCP key** — `POST /v1/dev/rotate-key` using the **new
      user's access token** (new `PamClient.rotate_developer_key()` method).
      Returns `pam_mkey_<prefix>.<secret>`; store it for the answer phase.
3. **`answer_batch(prompts)`** — for each batch of questions:
   - Render the numbered `Q1..QN` prompt (`render_batch_prompt`, shared).
   - Run **one Claude Code invocation** with:
     - `mcp_servers` = the PAM Memory MCP config (URL + `Authorization` header
       carrying the `pam_mkey`),
     - `allowed_tools = ["mcp__pam_memory__retrieve_memory"]`,
     - `system` = the PAM MCP system-prompt snippet (see below),
     - `prompt` = `answer_prompt(rendered)` (instructs the agent to call
       `retrieve_memory` then answer the numbered questions).
   - Parse with `parse_batch_response`. Keep the **same 0/N retry + inter-batch
     sleep** behaviour as `PamBaseline` / `McpHarnessBaseline`.
4. **`cleanup_sample()`** — `PamClient.delete_account(user_id)` (skipped under a
   backup flag, mirroring `pam`).
5. **`teardown()`** — `harness.teardown()` (no-op today).

---

## Key endpoints, constants & auth

Verified against `pam-agent-api`:

- **rotate-key**: `POST /v1/dev/rotate-key`
  - Router prefix `/dev` is gated by `require_feature_flag(FeatureFlagEnum.MEMORY_MCP)`
    and authenticated by the **caller's own access token** → must be called as
    the freshly-created benchmark user (whose token `create_account` already set).
  - Response model `DeveloperRotateApiKeyResponse`: `{ api_key, key_prefix, rotated_at }`.
    `api_key` is the full `pam_mkey_<prefix>.<secret>`.
- **MCP server URL**: `https://staging.api.pam.harmix.ai/v1/mcp/memory`
  (per task instructions). Plan: derive it from `PAM_API_HOST` as
  `f"{host}/v1/mcp/memory"` with an explicit override env var
  `PAM_MCP_MEMORY_URL` (defaulting to the staging URL).
- **MCP server config** (written by `ClaudeCodeHarness` to a temp `--mcp-config`
  file; the harness already supports the `mcp_servers` dict + `--strict-mcp-config`):
  ```json
  {
    "mcpServers": {
      "pam_memory": {
        "type": "http",
        "url": "https://staging.api.pam.harmix.ai/v1/mcp/memory",
        "headers": { "Authorization": "pam_mkey_<prefix>.<secret>" }
      }
    }
  }
  ```
  Note: the `Authorization` value is the **raw key** (no `Bearer ` prefix) — this
  matches `pam-agent-api`'s `_claude_code_config_example`.
- **Tool name in the harness**: Claude Code namespaces MCP tools as
  `mcp__<server>__<tool>` → `mcp__pam_memory__retrieve_memory`. The server
  exposes a single tool, `retrieve_memory` (input: `prompt`, optional
  `session_id`).
- **System prompt** (required per the docs; passed via `--append-system-prompt`).
  Copy `MEMORY_MCP_SYSTEM_PROMPT_SNIPPET` verbatim from pam-agent-api:
  > "You have access to PAM Memory through the retrieve_memory MCP tool. Use it
  > when a request may depend on company-specific context: people, projects,
  > decisions, processes, priorities, history, customers, documents, meetings,
  > or internal terminology. Prefer retrieving memory before making assumptions.
  > If retrieved context is partial or uncertain, say so and ask a focused
  > follow-up."

Env vars used (all already loaded via `src/env.py`): `PAM_API_HOST`,
`PAM_API_USER`, `PAM_API_PASSWORD`, plus optional `PAM_MCP_MEMORY_URL`. No
`PAM_API_KEY` needed (rotate-key uses the user's own access token, not the admin
api-key path).

---

## File-by-file changes

### New package: `src/baselines/pam_mcp/`

- **`__init__.py`** — empty package marker.
- **`baseline.py`** — `PamMcpBaseline(BaselineBase)`:
  - `name = "pam_mcp"`, `track = "agentic_memory"`, `external_memory = True`.
  - `__init__(*, harness, harness_model, output_root, batch_size=10,
    max_turns=None, mcp_url=None, backup_memory=False, **_ignored)`:
    builds `PamClient(require("PAM_API_HOST"))`, reads admin creds from
    `PAM_API_USER`/`PAM_API_PASSWORD`, resolves `mcp_url` (env/override/default),
    stores the harness. Accepts and ignores harness kwargs it doesn't use
    (e.g. `keep_memory`) via `**_ignored`, matching `McpHarnessBaseline`.
  - Lifecycle methods per the flow above. `answer_batch` reuses the
    token-distribution logic from `McpHarnessBaseline.answer_batch`
    (input = fresh + cache-read + cache-write, split with `distribute`;
    `injected_tokens`/`enriched_*` left `None`).
  - `extras()` / `baseline_kwargs_extra()` surfacing `pam_user_id`,
    `memory_creation_duration_sec`, `harness`, `harness_model`, `batch_size`,
    `memory_run_ids`, harness session ids, and the `key_prefix` (never the
    secret).
- **`prompts.py`** — `SYSTEM_PROMPT` (the verbatim snippet) and
  `answer_prompt(batch_prompt)` (wraps the numbered batch with an instruction to
  call `retrieve_memory` first, then answer every question; read-only — there is
  no ingest prompt because memory is built server-side).

### `src/baselines/pam/client.py`

- Add **`rotate_developer_key(self) -> str`**: `POST {base_url}/dev/rotate-key`
  with `self._headers()` (the per-user bearer), single 401 refresh-and-retry +
  `_raise_for_auth`, returns `data["api_key"]`. Update the module docstring's
  endpoint list.

### `src/registry.py`

- Add `"pam_mcp"` to `_BASELINE_ALIASES`.
- In `get_baseline`, branch **before** the `_MCP_BACKENDS` check:
  ```python
  if name == "pam_mcp":
      from baselines.pam_mcp.baseline import PamMcpBaseline
      harness_name = kwargs.pop("harness", None) or "claude-code"
      harness_model = kwargs.pop("harness_model", None)
      harness = get_harness(harness_name, model=harness_model, max_turns=kwargs.get("max_turns"))
      return PamMcpBaseline(harness=harness, harness_model=harness_model, **kwargs)
  ```
  (Same composition shape as `_build_mcp_baseline`.)

### `src/runner.py`

- No change required. When `--harness` is set (it is, for `run_mcp_benchmark.py`),
  the existing `if cfg.harness:` branch already passes `harness`, `harness_model`,
  `output_root`, `batch_size`, `keep_memory`, `max_turns` into `get_baseline` —
  which is exactly what `PamMcpBaseline` consumes. The run lands in
  `locomo_mcp_results` automatically (`cfg.harness` truthy).

### `src/mcp_cli.py` / `scripts/run_mcp_benchmark.py`

- No structural change. Users select the baseline with `--baseline pam_mcp`.
  Optionally update the `--baseline` help text and the module docstring usage
  example to mention `pam_mcp`. If a backup flag is desired, thread a
  `--mcp-keep-account`-style option through `RunConfig` → `baseline_extra`
  (optional; can default to delete, matching `pam`).

---

## Token & cost accounting

Use the **harness-reported** usage (same as `McpHarnessBaseline`), since
answering runs on Claude Code, not Pam's agent:

- `input_tokens = result.input_tokens + cache_read + cache_write`, split evenly
  across the batch with `distribute`.
- `output_tokens`, `cache_read`, `cache_write`, `est_cost_usd` from the harness
  result, per-question split.
- `injected_tokens` / `enriched_user_prompt_tokens` → `None` (Pam-chat concepts
  that don't apply here).
- `prompt_tokens` counted from the rendered batch with the harness model's
  tokenizer (`count_tokens`).

`memory_creation_duration_sec` measured around `process_generic_files` +
`wait_for_memory` (the Pam build), as in `pam`.

---

## Prerequisites & risks (verify during implementation)

1. **`MEMORY_MCP` feature flag must be enabled for benchmark accounts.**
   `/v1/dev/*` (incl. rotate-key) returns **403** unless the user's resolved
   `MEMORY_MCP` flag is on. New `POST /v1/admin/create-account` accounts default
   to the TRIAL plan, which grants no flags.
   **Resolved (plan-based):** `create-account` now takes a `plan` query param.
   `pam_mcp` creates each account on the **`dev` plan**, which seeds the `dev`
   plan's feature flags — including `MEMORY_MCP` — via
   `credits_service.set_user_plan` + `feature_flag_repository.seed_flags_for_user_by_plan`
   (the same two calls Stripe makes on `subscription_create`).
   `provisioner_service.create_client` still runs for every plan (so the memory
   pipeline has its provisioned client). No separate enable-flag call is needed,
   so a normal `pam_mcp` run does **not** require `PAM_API_KEY` (only the
   `--pam-debug-user-id` reuse path does, exactly like `pam`).
2. **Memory readiness.** `retrieve_memory` needs the user's memory in a `Ready`
   state. We already block on `wait_for_memory` (pipeline `completed`); if MCP
   retrieval still returns empty, add an optional `GET /v1/dev/readiness` poll
   before answering. Treat as a follow-up if the pipeline-complete signal proves
   sufficient.
3. **MCP transport.** Confirm Claude Code's `--mcp-config` accepts the
   `"type": "http"` remote-server shape used above (the harness writes exactly
   the dict it's given). Validate during an M0 smoke run with one sample /
   `--max-questions 2`.
4. **Quotas / rate limits** on the Memory MCP endpoint for staging benchmark
   accounts — watch for `quota_exceeded` tool results in batch runs.

---

## Testing

Mirror the existing `tests/baselines/pam` and `tests/baselines/mcp` suites:

- `tests/baselines/pam_mcp/test_baseline_lifecycle.py` — fake `PamClient` +
  fake harness; assert ordering (login → create → process → wait → rotate-key →
  answer → delete) and that the MCP config / system prompt / allowed-tools are
  passed to `harness.run`.
- `test_rotate_key_client.py` — `rotate_developer_key` posts to the right URL
  with the per-user bearer and parses `api_key`; 401-refresh path.
- Reuse the shared batch-protocol tests (render/parse/distribute) — no new copy
  needed.
- `tests/test_registry.py` — `get_baseline("pam_mcp", harness=..., ...)` returns
  a `PamMcpBaseline` and `"pam_mcp"` is in `known_baselines()`.

Smoke run:
```bash
uv run python scripts/run_mcp_benchmark.py \
    --dataset locomo --harness claude-code --baseline pam_mcp \
    --harness-model <vertex-model-id> --exp-name mcp_locomo_pam_v1 \
    --mcp-batch-size 10 --sample-index 0 --max-questions 2 --no-mongo
```

---

## Implementation status (done)

- **pam-agent-api** (branch `feature/PAM-1155/add-memory-mcp-flag-endpoint`):
  `POST /v1/admin/create-account` gained a `plan` query param that seeds the
  plan's credits + feature flags (`create_client` runs for every plan). Ported
  from pam-backend-api: `PLAN_FEATURE_FLAGS` (`app/core/user_plans.py`),
  `CreditsService.set_user_plan`, and
  `FeatureFlagRepository.seed_flags_for_user_by_plan`.
- **pam-benchmark**:
  - `PamClient.create_account(plan=…)` + `PamClient.rotate_developer_key`.
  - `src/baselines/pam_mcp/` (`baseline.py`, `prompts.py`).
  - `registry.py` (`pam_mcp` alias + `_build_pam_mcp_baseline`),
    `runner.py` (forwards `debug_user_id` / `backup_memory` for `pam_mcp`),
    `mcp_cli.py` (`--pam-debug-user-id`, `--backup-memory`).
  - Per the feedback: the answer loop keeps the **same retries (0/N → 2 retries,
    exp. backoff), inter-batch sleep, and polling** as the `pam` baseline, and
    `--backup-memory`, `--save-responses`, `--pam-debug-user-id` all work for
    `pam_mcp`.
  - Tests: `tests/baselines/pam_mcp/` (lifecycle, MCP wiring, token mapping,
    retries, backup/debug knobs) + `tests/test_registry.py` cases. Full suite
    green (224 passed).

## Out of scope / open questions

- Datasets other than LoCoMo (memtrack, longmemeval) — not wired in registry yet.
- OAuth/browser MCP flow — we use the static `pam_mkey` (API-key) path only.
- Reusing an existing Pam user (`--pam-debug-user-id` equivalent) for `pam_mcp` —
  deferred; a debug-reuse path would also need to re-mint/rotate the key.
- Whether to key the MCP `session_id` to the sample id for server-side triage
  logging — nice-to-have, not required.
