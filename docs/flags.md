# CLI Flags Reference

Every flag exposed by the four entrypoints, which datasets and baselines it
applies to, and exactly how the conditional ones resolve.

> **Maintenance:** this file is the single source of truth for flags. Whenever a
> flag is added, removed, renamed, or its default/condition changes in
> [`src/cli.py`](../src/cli.py), [`src/mcp_cli.py`](../src/mcp_cli.py),
> [`scripts/generate_report.py`](../scripts/generate_report.py) or
> [`scripts/download_data.py`](../scripts/download_data.py), update this file in
> the same change.

## Entrypoints

| Script | CLI module | What it runs |
|---|---|---|
| `scripts/run_benchmark.py` | [`src/cli.py`](../src/cli.py) | Classic runs: LiteLLM models and the `pam` HTTP-API baseline |
| `scripts/run_mcp_benchmark.py` | [`src/mcp_cli.py`](../src/mcp_cli.py) | Memory-on-agentic-harness runs: `memory_md_mcp`, `pam_mcp` |
| `scripts/generate_report.py` | same file | Renders an HTML/Markdown report from Mongo |
| `scripts/download_data.py` | same file | Verifies/downloads dataset files |

Both run scripts build the same [`RunConfig`](../src/config.py) and delegate to
[`runner.run`](../src/runner.py); the split exists only so the two experiment
types stay legible.

## Dataset × baseline support

Not every combination is runnable — flags follow from this table.

| Baseline | LoCoMo | Harmix | Entrypoint | Memory |
|---|---|---|---|---|
| LiteLLM ids (`gpt-4-turbo`, `gpt-4o`, `gpt-4o-mini`, `gpt-4`, `gpt-3.5-turbo`, …) | ✅ | ❌ (no conversation to pack into the prompt) | `run_benchmark.py` | none |
| `pam` | ✅ | ❌ (`PamBaseline.prepare_for_sample` serializes a LoCoMo conversation) | `run_benchmark.py` | Pam API |
| `memory_md_mcp` | ✅ | ❌ (`conversation_to_transcript` needs `sample.conversation`) | `run_mcp_benchmark.py` | Markdown files on disk |
| `pam_mcp` | ✅ | ✅ (memory built from the persona's GCS snapshot) | `run_mcp_benchmark.py` | Pam API + PAM Memory MCP |

---

## `scripts/run_benchmark.py`

| Flag | Type / default | Applies to | Meaning |
|---|---|---|---|
| `--dataset` | str, **required** | all | Dataset name. Registered: `locomo`, `harmix` (see [`src/registry.py`](../src/registry.py)). In practice this script is LoCoMo-only — see the support table above. |
| `--baseline` | str, **required** | all | Baseline name. Any registered alias (`pam`, `gpt-4-turbo`, …); an unknown name is treated as a LiteLLM model id. |
| `--exp-name` | str, **required** | all | Experiment identifier. Groups Mongo rows, `outputs/`, and reports. Multi-seed = same `--exp-name`, different `--seed`. |
| `--task` | str, default `None` | all | Task pipeline name. **Conditional default:** falls back to `--dataset` (`RunConfig.resolved_task()`). Only useful when a dataset is scored by a different pipeline. |
| `--seed` | int, default `42` | all | Seeds Python/NumPy/`PYTHONHASHSEED` via [`seeds.seed_all`](../src/seeds.py), is passed to LiteLLM as a completion `seed`, and becomes the last path segment of the output dir. |
| `--sample-index` | int, default `None` | all | Run only this sample index. **Default (unset):** all samples, `range(loader.num_samples())`. |
| `--max-questions` | int, default `None` | all | Cap questions per sample (debug). **Default (unset):** all questions. Recorded in Mongo as `max_questions` (`0` when unset). |
| `--baseline-model` | str, default `None` | LiteLLM baselines | Overrides the model id resolved from `--baseline`. Also used as the `model_name` label in the task pipeline. Ignored by `pam` (Pam picks its own agent model). |
| `--baseline-kwargs` | JSON str, default `{}` | all | Extra kwargs splatted into the baseline constructor. Invalid JSON → `typer.BadParameter`. Per-baseline keys are listed [below](#baseline-kwargs). |
| `--judge-model` | str, default `gpt-4o` | all | Model for the LLM-as-a-Judge pass. Unlike the MCP CLI, this default is **not** dataset-conditional. |
| `--judge-concurrency` | int, default `8` | all | Max concurrent judge calls. |
| `--output-dir` | path, default `None` | all | **Conditional default:** `outputs/<exp-name>/<seed>/`. Holds `config.yaml`, `metrics.json`, and `responses.log` when `--save-responses` is set. |
| `--no-mongo` | flag, default off | all | Skip all MongoDB writes (`RunConfig.mongo = False`). Local `outputs/` artifacts are still written. |
| `--dry-run` | flag, default off | all | Resolve config, log which samples *would* run, skip answering/judging/Mongo. `config.yaml` and an empty-sample `metrics.json` are still written. |
| `--save-responses` | flag, default off | all | Append every batch's raw prompt, raw model response, expected answers, and parsed answers to `responses.log` in the output dir, flushed per batch so it can be tailed live. |
| `--log-format` | `rich` \| `json`, default `rich` | all | `json` emits structured logs for Cloud Logging; use it for Cloud Run Jobs. |
| `--pam-batch-size` | int, default `10` | **`pam` only** | Questions per SSE chat call (one memory retrieval shared by the batch). Silently ignored by every other baseline — LiteLLM baselines are hardcoded to `batch_size = 1`. |
| `--pam-debug-user-id` | int, default `None` | **`pam` only** | Reuse an existing Pam user id (and its already-built memory) instead of creating an account, uploading the conversation, and polling the memory pipeline. Needs `PAM_API_KEY`. Also suppresses account deletion in `cleanup_sample`. |
| `--backup-memory` | flag, default off | **`pam` only** | Keep each conversation's Pam account after the run (no delete-account call) so its memory can be reused later via `--pam-debug-user-id`. |
| `--pam-exp-config` | str, default `None` | **`pam` only** | Experiment-registry preset for the memory build (e.g. `introspective_v2`). Sent as the `experiment` field on the `process-generic-files` POST; agent-api relays it to the memory pipeline as `--experiment` ([`memory_pipeline_workflow.yaml.tftpl`](../../pam-infrastructure/modules/memory-workflows/memory_pipeline_workflow.yaml.tftpl)). **Unset ⇒** the wire field is omitted ⇒ the pipeline's `baseline` preset (unchanged behavior). Stamped onto each Mongo result doc as the **`pam_exp_config`** column (defaulting to `"baseline"`), so several arms under one `--exp-name` are groupable/comparable. **Do NOT combine with `--pam-debug-user-id` / `--backup-memory`** — those reuse an account and skip the build, so the preset never takes effect. |

**Conditional forwarding.** `--pam-batch-size`, `--pam-debug-user-id`,
`--backup-memory`, and `--pam-exp-config` are only forwarded to the baseline when `--baseline pam`
([`runner.py`](../src/runner.py) `_run_async`). For any other baseline they are
parsed, stored in `RunConfig`, written to `config.yaml`, and otherwise inert.

---

## `scripts/run_mcp_benchmark.py`

| Flag | Type / default | Applies to | Meaning |
|---|---|---|---|
| `--exp-name` | str, **required** | all | As above. |
| `--dataset` | str, default `locomo` | all | `locomo` \| `harmix`. Drives three conditional defaults (`--mcp-batch-size`, `--raw-prompt`, `--judge-model`) and selects the aggregation path in the runner (Harmix is judge-only: no token-F1, no categories, gold-less cases excluded from the denominator). |
| `--harness` | str, default `claude-code` | all | Agentic harness. `claude-code` is the only registered value; anything else raises. Also becomes a path segment in the default output dir. |
| `--baseline` | str, default `memory_md_mcp` | all | `memory_md_mcp` \| `pam_mcp`. |
| `--harness-model` | str, default `None` | all | Base model id for the harness (a Vertex Claude id). **Default (unset):** whatever the `claude` CLI resolves on its own. This is the MCP-CLI analogue of `--baseline-model`, which does not exist here. |
| `--task` | str, default `None` | all | Defaults to `--dataset`. |
| `--seed` | int, default `42` | all | As above. |
| `--sample-index` | int, default `None` | all | Run only this sample index. **Default (unset):** all samples. |
| `--sample-id` | str, default `None` | **Harmix only** | Select one sample by string id (`nazar`, `nazar_mini`, `oleksandr`, `nick` — whatever the bench-cases JSON defines). **Wins over `--sample-index`.** Raises `--sample-id is not supported for dataset '<name>'` for loaders without `index_for_sample_id`, i.e. for LoCoMo. |
| `--max-questions` | int, default `None` | all | Cap questions per sample (debug). |
| `--mcp-batch-size` | int, default `None` | all | Questions per answer batch. **Conditional default:** `1` for `--dataset harmix`, `10` otherwise. **Forced to `1`** whenever `--raw-prompt` is on, regardless of what was passed. |
| `--mcp-keep-memory` | flag, default off | **`memory_md_mcp` only** | Keep the per-sample on-disk memory (`<output-dir>/<sample_id>/memory/`) after the run, and reuse it if already present instead of rebuilding. Default wipes it. `pam_mcp` ignores this (its memory lives server-side in Pam — use `--backup-memory` there instead). |
| `--mcp-max-turns` | int, default `None` | all | Cap agent turns per harness invocation (`claude --max-turns`). **Default (unset):** no cap. |
| `--mcp-max-retries` | int, default `None` | **`pam_mcp`** (see below) | Retries when a batch comes back empty (0/N) or answered without calling `retrieve_memory` (`num_turns < 2`); retries escalate the prompt to force the tool call. **Default (unset):** `2`. Raise it for noisier environments. `memory_md_mcp` swallows the kwarg. |
| `--samples-per-question` | int, default `1` | **`pam_mcp` + `--raw-prompt`** (harmix) | **avg@k**: generate K independent responses per question (in parallel via a pool of K sessions, one question at a time with a barrier), judge each, and report **avg@k** (mean of per-question fraction-correct) with `judge_accuracy_std`. The report shows the single answer **closest to the mean score**; the K raw answers are not stored. **Default 1** = one response/question, no extra cost. K>1 multiplies generation + judge cost by K. Ignored outside the `pam_mcp` raw path. |
| `--raw-prompt` / `--no-raw-prompt` | tri-state bool, default `None` | **`pam_mcp` only** (see below) | Ask one question at a time with no numbered-batch answer scaffolding (so the agent answers naturally instead of a terse `A1: <short answer>` line). The dataset's question is carried through inside a **mandatory-retrieval directive** that requires calling `retrieve_memory` before answering — the soft system prompt alone let the agent skip the tool. **Conditional default:** on for `--dataset harmix`, off otherwise. |
| `--judge-model` | str, default `None` | all | **Conditional default:** `claude-sonnet-4-5` for `--dataset harmix`, `gpt-4o` otherwise. Harmix judging additionally honors each case's `grading_notes` (`judge_many_with_notes`). |
| `--judge-concurrency` | int, default `8` | all | Max concurrent judge calls. |
| `--output-dir` | path, default `None` | all | **Conditional default:** `outputs/<exp-name>/<harness>/<seed>/` — the extra `<harness>` segment (inserted whenever `harness` is set) keeps multiple harnesses under one experiment from colliding. Doubles as the harness's per-sample working area. |
| `--no-mongo` | flag, default off | all | Skip Mongo writes. |
| `--dry-run` | flag, default off | all | Resolve config and exit without answering/judging. |
| `--save-responses` | flag, default off | all | Writes `responses.log` (Q/A + raw prompts/responses) **and** `harness.log` — the full harness transcript (thinking, tool calls, JSON events) — into the output dir. Both are truncated at the start of each run. |
| `--baseline-kwargs` | JSON str, default `{}` | all | Extra baseline kwargs; see [below](#baseline-kwargs). |
| `--log-format` | `rich` \| `json`, default `rich` | all | As above. |
| `--pam-debug-user-id` | int, default `None` | **`pam_mcp` only** | Reuse an existing Pam user id and its built memory instead of creating an account and building memory. Needs `PAM_API_KEY`. |
| `--backup-memory` | flag, default off | **`pam_mcp` only** | Keep the per-sample Pam account after the run (no delete-account) so its memory can be reused later via `--pam-debug-user-id`. |
| `--pam-exp-config` | str, default `None` | **`pam_mcp` only** | Experiment-registry preset for the memory build (e.g. `introspective_v2`). Sent as the `experiment` field on the `process-snapshot` (harmix) / `process-generic-files` POST; agent-api relays it to the memory pipeline as `--experiment` ([`memory_pipeline_workflow.yaml.tftpl`](../../pam-infrastructure/modules/memory-workflows/memory_pipeline_workflow.yaml.tftpl)). **Unset ⇒** the wire field is omitted ⇒ the pipeline's `baseline` preset. Stamped onto each Mongo result doc as the **`pam_exp_config`** column (defaulting to `"baseline"`), so several arms under one `--exp-name` are groupable/comparable (the harmix report shows an *Exp config* column + header when >1 preset is present). **Do NOT combine with `--pam-debug-user-id` / `--backup-memory`** (they skip the build, so the preset never takes effect). |

**Conditional forwarding.** `--pam-debug-user-id`, `--backup-memory`, and `--pam-exp-config` are only
forwarded when `--baseline pam_mcp`; with `memory_md_mcp` they are parsed and
ignored.

**`--raw-prompt` caveat.** `PamMcpBaseline` honors it (skips
`render_batch_prompt`/`parse_batch_response` and wraps the single question in a
mandatory-retrieval directive via `prompts.raw_answer_prompt`).
`McpHarnessBaseline` (`memory_md_mcp`) does **not** — it swallows the kwarg, so
passing `--raw-prompt` there only has the side effect of pinning the batch size
to 1 while the numbered Q/A protocol still applies.

### Resolution order for the conditional MCP defaults

Applied in [`src/mcp_cli.py`](../src/mcp_cli.py) after parsing, and only to flags
left unset:

1. `raw_prompt is None` → `raw_prompt = (dataset == "harmix")`
2. `mcp_batch_size is None` → `1` if `dataset == "harmix"` else `10`
3. `raw_prompt` truthy (explicit or defaulted) → `mcp_batch_size = 1`, overriding step 2 *and* any explicit `--mcp-batch-size`
4. `judge_model is None` → `claude-sonnet-4-5` if `dataset == "harmix"` else `gpt-4o`

So `--dataset harmix --mcp-batch-size 10` still runs with batch size 1 unless you
also pass `--no-raw-prompt`.

---

## `scripts/generate_report.py`

| Flag | Type / default | Meaning |
|---|---|---|
| `--exp-name` | str, **required** | Experiment to render. Exits with code 1 if no matching Mongo documents exist. |
| `--dataset` | str, default `locomo` | Selects the collection (`<dataset>_results`) and the Jinja template (Harmix has its own, `report_harmix.html.j2`). |
| `--output-dir` | path, default `None` | **Conditional default:** `reports/<exp-name>/`. |
| `--format` | `html` \| `md`, default `html` | Writes `report.html` or `report.md`. Any other value exits with code 1. |
| `--mcp` | flag, default off | Read `<dataset>_mcp_results` instead of `<dataset>_results` — required for anything produced by `run_mcp_benchmark.py`, since the runner routes harness runs to the `_mcp_results` collection. |
| `--collection` | str, default `None` | Explicit collection override. **Wins over `--mcp`** (`collection or (f"{dataset}_mcp_results" if mcp else None)`). |

## `scripts/download_data.py`

| Flag | Type / default | Meaning |
|---|---|---|
| `--dataset` | str, **required** | `locomo` \| `harmix`. Anything else exits with code 1. |
| `--force` | flag, default off | **`locomo` only** — re-download even if the file is present. LoCoMo downloading is not implemented (upstream licensing), so `--force` currently just skips the "file present" short-circuit and prints the manual-download instructions. Ignored for `harmix`, which always performs a live GCS reachability check. |

---

## Baseline kwargs

`--baseline-kwargs '{"key": value}'` is merged into the constructor call in
[`registry.get_baseline`](../src/registry.py). Runner-supplied keys
(`harness`, `harness_model`, `output_root`, `batch_size`, `keep_memory`,
`max_turns`, `raw_prompt`, `save_responses`, `debug_user_id`, `backup_memory`)
take precedence over anything you pass here, so use it for the knobs below.

| Baseline | Accepted keys |
|---|---|
| LiteLLM (`gpt-4o`, …) | `temperature` (default `0.0`), `max_tokens` (default `1024`), `rpm`, `completion_kwargs` (dict passed straight to `litellm.acompletion`), `name` |
| `pam` | `host`, `admin_email`, `admin_password`, `api_key` (each defaults to the corresponding `PAM_API_*` env var) |
| `pam_mcp` | `host`, `admin_email`, `admin_password`, `api_key`, `mcp_url` (defaults to `<PAM_API_HOST>/v1/mcp/memory`) |
| `memory_md_mcp` | none beyond the runner-supplied set |

`pam`, `pam_mcp`, and `memory_md_mcp` silently swallow unknown keys (`**_ignored`);
LiteLLM baselines raise a `TypeError` on them — a useful typo check.

## Environment variables that act like flags

Not CLI flags, but they change behavior the same way. Loaded from a gitignored
`secrets.env` (or `.env`) by [`env.load_secrets`](../src/env.py); in Cloud Run
Jobs they come from Secret Manager.

| Variable | Required for | Effect |
|---|---|---|
| `OPENAI_API_KEY` | LiteLLM baselines, `gpt-4o` judging | Provider key. |
| `CONNECTION_STRING`, `DB_NAME` | any run without `--no-mongo` | Mongo target. |
| `PAM_API_HOST`, `PAM_API_USER`, `PAM_API_PASSWORD` | `pam`, `pam_mcp` | Pam API host + admin login. Missing → `RuntimeError: required env var not set`. |
| `PAM_API_KEY` | `--pam-debug-user-id` reuse | Mints a per-user token via the api-key-gated admin endpoint. Unused on a normal run. |
| `PAM_MCP_MEMORY_URL` | `pam_mcp` (optional) | Overrides the Memory MCP server URL; same as the `mcp_url` baseline kwarg. |
| `PAM_OUTPUT_TOKEN_MODEL` | `pam` | Token-counter model id used to estimate Pam's output tokens. |
| `DATABASE_HOST` / `DATABASE_PORT` / `DATABASE_NAME` / `DATABASE_USERNAME` / `DATABASE_PASSWORD` | `pam` (optional) | Agent-side token metrics read from Pam's metrics DB. |
| `VERTEX_PROJECT_ID`, `VERTEX_REGION`, `VERTEX_CREDENTIALS` | any `--harness claude-code` run | Vertex AI auth for the Claude Code CLI. |
| `HARMIX_BENCH_CASES_URI` | `--dataset harmix` (optional) | Overrides the bench-cases source (a local path or a `gs://` URI); default is `gs://pam-dev-memory-data/benchmark/datasets/harmix/harmix_bench_cases.json`. |
| `MCP_TIMEOUT` | MCP runs (optional) | MCP server startup timeout in ms; harness default `60000`. |
| `MCP_TOOL_TIMEOUT` | MCP runs (optional) | Per-tool-call wall-clock timeout in ms; harness default `600000` (a large `retrieve_memory` can run well past Claude Code's ~60s default). |
| `PYTHONHASHSEED` | all | Set by `seeds.seed_all` from `--seed`; do not set by hand. |

## Worked examples

```bash
# LoCoMo smoke run — 1 sample, 5 questions, no Mongo
uv run python scripts/run_benchmark.py \
  --dataset locomo --baseline gpt-4-turbo --exp-name local_smoke \
  --sample-index 0 --max-questions 5 --no-mongo

# LoCoMo through Pam's HTTP API, reusing a pre-built memory
uv run python scripts/run_benchmark.py \
  --dataset locomo --baseline pam --exp-name pam_locomo_v1 \
  --pam-batch-size 10 --pam-debug-user-id 1234 --save-responses

# LoCoMo on Claude Code + Memory.md, keeping the on-disk memory for inspection
uv run python scripts/run_mcp_benchmark.py \
  --dataset locomo --harness claude-code --baseline memory_md_mcp \
  --harness-model <vertex-claude-model-id> --exp-name mcp_locomo_md_v1 \
  --mcp-batch-size 10 --mcp-keep-memory

# Harmix persona bench on Claude Code + PAM Memory MCP.
# Implied by --dataset harmix: --mcp-batch-size 1, --raw-prompt,
# --judge-model claude-sonnet-4-5.
uv run python scripts/run_mcp_benchmark.py \
  --dataset harmix --harness claude-code --baseline pam_mcp \
  --harness-model <vertex-claude-model-id> --exp-name harmix_v1 \
  --sample-id oleksandr --save-responses --backup-memory

# Report for an MCP run (note --mcp: different Mongo collection)
uv run python scripts/generate_report.py \
  --exp-name harmix_v1 --dataset harmix --mcp --format html
```
