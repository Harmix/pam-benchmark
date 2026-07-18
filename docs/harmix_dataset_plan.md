# Harmix dataset — `claude-code + pam_mcp` integration plan

Integrate the **Harmix** golden-persona bench (`src/datasets/harmix/data/harmix_bench_cases.json`)
into the MCP-memory-on-harness experiment (`scripts/run_mcp_benchmark.py`), mirroring
the LoCoMo `pam_mcp` flow but building each memory from a **pre-staged GCS snapshot**
instead of an uploaded conversation file.

## Dataset shape

`harmix_bench_cases.json` has three top-level keys:

- `environments` — one per persona (`nazar`, `nazar_mini`, `oleksandr`,
  `nick`). Each carries `id`, `memory_sources` (e.g. `["emails", "meetings"]`)
  and `memory_snapshot` (a `gs://…zip` URI with all raw source context for that
  persona).
- `cases` — `{"<env_id>_cases": [ {id, environment, question, context,
  expected_answer, grading_notes}, … ]}`.
- `_meta` — field docs.

**Mapping to the LoCoMo mental model**

| LoCoMo | Harmix |
|---|---|
| conversation / sample | **environment** (persona) |
| `sample.qa[]` | the env's cases |
| upload conversation file → build memory | **copy `memory_snapshot` zip → trigger pipeline from extract** |
| one Pam account per conversation | **one Pam account per environment** |

## Memory build — how it differs from LoCoMo `pam_mcp`

LoCoMo `pam_mcp` calls `POST /v1/memory/process-generic-files/{user_id}`; server-side that
zips the upload to `gs://pam-{env}-memory-data/users/{user_id}/{run_id}/state_after_sources_download.zip`
and publishes a Pub/Sub `RunRequested(run_type="generic_source_no_restore")`. The Cloud
Workflow then **skips `sources_download` and starts at `extract`**.

Harmix reuses that exact skip-to-extract path, but:

1. The zip already exists (the env's `memory_snapshot`), so the **pam-agent-api endpoint**
   mints the `run_id` and **copies** it (GCS→GCS) to
   `gs://pam-dev-memory-data/users/{NEW_USER_ID}/{RUN_ID}/state_after_sources_download.zip`
   instead of the benchmark uploading files. The benchmark never touches GCS.
2. The zip holds **real** source data (emails, meetings), so the pipeline must run the real
   `gmail` / `meeting_transcripts` extractors — driven by an explicit **`--sources`** list
   derived from the env's `memory_sources`. The generic path hardcodes `sources="generic"`.

### Source-name mapping (benchmark → pipeline)

`memory_sources` tokens → extract handler keys (`extract.py::ALL_SOURCES`):

| memory_sources | `--sources` |
|---|---|
| `emails` | `gmail` |
| `meetings` | `meeting_transcripts` |

Unknown tokens pass through unchanged.

## End-to-end trigger (cross-repo)

```
pam-benchmark          POST /v1/memory/process-snapshot/{uid} {snapshot_uri, sources:[gmail,meeting_transcripts]}
      ▼
pam-agent-api          mint run_id; copy snapshot_uri ──GCS──▶ users/{uid}/{run_id}/state_after_sources_download.zip
      │                publish RunRequested(run_type=generic_source_no_restore,
      │                                     requested_by=user_added_generic_files_no_restore,
      │                                     run_id, sources)                     ← publisher gains `sources`
      ▼  Pub/Sub → Eventarc → dispatch Workflow (infra: maps message.sources → --sources)
pam-jobs dispatch.py   --sources … → logic.dispatch_run_requested(sources=…)     ← new arg
      │                → _dispatch_generic_source_no_restore(sources=…)          ← argument["sources"]=sources or "generic"
      ▼  Cloud Workflow (infra): check_skip_sources_download → stage_2_extract --sources {sources}
pam-jobs extract.py    run_extract(sources={gmail, meeting_transcripts})  (skips sources_download)
```

Then the benchmark polls `GET /v1/memory/get-memory-pipeline-status/{uid}/{run_id}` (unchanged)
and, once `completed`, mints a Memory MCP key and answers exactly like LoCoMo `pam_mcp`.

## Repo-by-repo changes

### pam-benchmark

- `src/datasets/harmix/schemas.py` — `HarmixCase`, `HarmixEnvironment`, `HarmixSample`
  (one per environment; `.qa` = its cases; exposes `environment`, `memory_sources`,
  `memory_snapshot`). Case exposes `.question`, `.expected_answer`, `.grading_notes`,
  and LoCoMo-compat shims (`.answer`, `.category=0`, `.evidence=[]`) so the shared task
  pipeline works unchanged.
- `src/datasets/harmix/loader.py` — `HarmixLoader` reading the JSON; `num_samples()` =
  number of environments; `get_sample(i)` = one env with its cases. Supports selecting a
  single env by id (for `--sample-id=oleksandr`).
- `src/baselines/pam_mcp/baseline.py` — make `prepare_for_sample` snapshot-aware: when the
  sample is a Harmix env, **call the new `process_snapshot` endpoint** (which mints the run_id,
  copies the zip, and triggers the pipeline) instead of `process_generic_files`. Everything
  else (poll, rotate-key, answer batches) is shared.
- `src/baselines/pam/client.py` — add `process_snapshot(snapshot_uri, sources) -> run_id`.
- `src/tasks/harmix/` — task pipeline (reuses the batch protocol; `external_memory=True`,
  bare per-question prompts) + prompts.
- `src/evals/llm_judge.py` — `grading_notes`-aware judge; default judge model for harmix =
  `claude-sonnet-4-5` (LiteLLM id). **No token-F1, no categories.**
- `src/runner.py` — dataset-aware aggregation/scoring/collection: harmix →
  `harmix_mcp_results`, judge with grading_notes, skip F1/category rollups. Null
  `expected_answer` cases are recorded but excluded from judge accuracy.
- `src/registry.py` — register `harmix` dataset + task.
- `src/mcp_cli.py` — add `--sample-id` (select env by id, e.g. `oleksandr`); default
  `--mcp-batch-size 1` for harmix; keep every existing flag (`--save-responses`,
  `--backup-memory`, `--pam-debug-user-id`, `--mcp-keep-memory`, `--mcp-max-turns`, …).
- `scripts/download_data.py` — verify `harmix_bench_cases.json` presence.
- `cluster/run_mcp_benchmark/Dockerfile` — add a build-time `test -f harmix_bench_cases.json`
  (already allow-listed in `.dockerignore`); add `google-cloud-storage` (already installed).
- `README.md` + this doc — document the new dataset.
- `tests/` — loader, source mapping, snapshot-trigger wiring (fake client), judge-with-notes.

### pam-agent-api

- `app/gateways/memory_pipeline_publisher.py` — `publish_run_requested(..., sources: list[str] | None = None)`
  → `payload["sources"] = ",".join(sources)`.
- `app/services/files/gcs_service.py` — `copy_object(src_uri, dst_blob_name)` (GCS→GCS
  rewrite within the memory bucket).
- `app/api/v1/memory/api.py` — new `POST /v1/memory/process-snapshot/{user_id}`
  `{snapshot_uri: str, sources: list[str]}`: token-owns-user check, mint `run_id`, copy
  `snapshot_uri` → `users/{user_id}/{run_id}/state_after_sources_download.zip`, publish
  RunRequested with `run_type=generic_source_no_restore`,
  `requested_by=user_added_generic_files_no_restore`, the minted `run_id`, and `sources`.
  Returns `{run_id, zip_uri, …}`. Shares `_publish_snapshot_run` with process-generic-files.

### pam-jobs

- `src/dispatcher/logic.py` — `dispatch_run_requested(..., sources: str | None = None)` →
  `_dispatch_generic_source_no_restore(..., sources=sources)`; there set
  `argument["sources"] = sources or "generic"`.
- `workflows/memory_update/dispatch.py` — add `--sources` arg → pass through.

### pam-infrastructure  *(out of the "benchmark+api+jobs" scope — flagged, diffs provided)*

- `modules/memory-pipeline/workflows/dispatch.yaml.tftpl` — map `message.sources` →
  `--sources` containerOverride for the dispatch job.
- `modules/memory-workflows/memory_pipeline_workflow.yaml.tftpl` — pass `--sources {sources}`
  to `stage_2_extract` (today extract gets only `common_args`, so it defaults to `ALL_SOURCES`).

> Note: even without the infra `--sources` on extract, the real extractors still process
> whatever is staged in the zip (they are data-driven), so harmix would build correctly with
> `ALL_SOURCES`; the infra change makes the run honor the explicit `--sources` and avoids
> running no-op extractors.

## Scoring

LLM-judge only, `claude-sonnet-4-5`, incorporating `grading_notes` when non-null. Token-F1
and LoCoMo category rollups are dropped for harmix. Cases with `expected_answer == null`
(open/draft tasks) are answered and recorded but excluded from judge-accuracy aggregation.

## CLI examples

```bash
# one environment (Oleksandr), first 2 questions, smoke
uv run python scripts/run_mcp_benchmark.py \
  --dataset harmix --harness claude-code --baseline pam_mcp \
  --harness-model <vertex-claude-id> --judge-model claude-sonnet-4-5 \
  --exp-name harmix_smoke --sample-id oleksandr --max-questions 2 \
  --mcp-batch-size 1 --save-responses --no-mongo

# full run, keep accounts for reuse
uv run python scripts/run_mcp_benchmark.py \
  --dataset harmix --harness claude-code --baseline pam_mcp \
  --harness-model <vertex-claude-id> --judge-model claude-sonnet-4-5 \
  --exp-name harmix_v1 --mcp-batch-size 1 --backup-memory
```
