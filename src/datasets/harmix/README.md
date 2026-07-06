# Harmix — golden-persona memory bench

A small, high-signal eval suite for **Pam Memory** quality. Each question is asked
against a **fixed per-person memory state** (an *environment*), so every query has a
known reference answer (or a rubric) to grade against — including the reasoning
behind it, not just isolated facts.

Data file: [`data/harmix_bench_cases.json`](data/harmix_bench_cases.json)
(≈40 KB, shipped with the repo). Per-persona **memory snapshots** live in GCS and are
read by the memory pipeline at run time (see [Memory build](#memory-build)).

## Layout

The JSON has three top-level keys:

- **`environments`** — one per persona. Each has `id`, `name`, `role`,
  `memory_sources` (which sources the memory is built from, e.g. `["emails", "meetings"]`),
  and `memory_snapshot` — a `gs://…state_after_sources_download.zip` with all raw source
  context for that persona.
- **`cases`** — `{"<env_id>_cases": [ … ]}`. Each case: `id`, `environment`, `source_id`,
  `question`, `context` (machine-readable memory scope), `expected_answer` (the gold/
  reference answer; `null` for open/draft tasks), and `grading_notes` (extra grading
  criteria, or `null`).
- **`_meta`** — field docs.

### Personas (environments)

| id | Who | Sources | Cases | Emphasis |
|---|---|---|---|---|
| `nazar` | Nazar — CEO / Co-founder | emails, meetings | 11 | Founder narrative, company facts, strategy |
| `oleksandr` (a.k.a. *Sasha*) | Oleksandr Kuprii — CTO / Co-founder | emails | 21 | Disambiguation & boundaries (two Yaroslavs, two Maksyms, three separate Adobe projects, Kazakhstan projects); a trap question that must not fabricate |
| `nick` | Nick Shcherban — VP of Partnerships | emails, meetings | 10 | Sales/partnership recall: clients, product & feature catalog, competitors, ICP-pivot rationale, client commitments |

## How it runs (mapping to the harness)

The Harmix dataset plugs into the **MCP-memory-on-harness** experiment
(`scripts/run_mcp_benchmark.py`) with the `pam_mcp` baseline, mirroring the LoCoMo
`pam_mcp` flow. The LoCoMo→Harmix analogy:

| LoCoMo | Harmix |
|---|---|
| one conversation = one sample | one **environment** (persona) = one sample |
| `sample.qa` | the environment's cases |
| one Pam account per conversation | **one Pam account per environment** |
| upload conversation → build memory | **copy snapshot zip → run pipeline from extract** |

### Memory build

Instead of uploading a conversation file, the persona's memory is built from its
pre-staged snapshot:

1. The benchmark creates one Pam account for the environment.
2. It calls `POST /v1/memory/process-snapshot/{user_id}` with the environment's
   `memory_snapshot` URI and the `--sources` list (its `memory_sources` mapped to
   pipeline keys: `emails → gmail`, `meetings → meeting_transcripts`).
3. Server-side, that copies the snapshot to
   `gs://pam-{env}-memory-data/users/{user_id}/{run_id}/state_after_sources_download.zip`
   and publishes a `RunRequested(run_type=generic_source_no_restore)`, so the Cloud
   Workflow **skips `sources_download` and starts at `extract`** for the given sources.
4. The benchmark polls `get-memory-pipeline-status` until `completed`, mints a Memory
   MCP key, and answers the persona's questions through the PAM Memory MCP tool.

The full cross-repo design (pam-agent-api / pam-jobs / pam-infrastructure changes) is in
[`docs/harmix_dataset_plan.md`](../../../docs/harmix_dataset_plan.md).

### Scoring

**LLM-judge only**, defaulting to **`claude-sonnet-4-5`**. When a case has
`grading_notes`, they are injected into the judge prompt as authoritative criteria
(e.g. *"Must disambiguate the two people named Yaroslav"*). Token-F1 and LoCoMo-style
categories do **not** apply. Cases with `expected_answer == null` (open/draft tasks such
as *"Write a reply draft to Paul…"*) are answered and recorded but excluded from judge
accuracy (`judged_count` is the denominator).

## Run it

```bash
# one persona, first 2 questions, smoke (no Mongo, save raw exchanges)
uv run python scripts/run_mcp_benchmark.py \
  --dataset harmix --harness claude-code --baseline pam_mcp \
  --harness-model <vertex-claude-id> --exp-name harmix_smoke \
  --sample-id oleksandr --max-questions 2 --save-responses --no-mongo

# full run across all three personas
uv run python scripts/run_mcp_benchmark.py \
  --dataset harmix --harness claude-code --baseline pam_mcp \
  --harness-model <vertex-claude-id> --exp-name harmix_v1
```

`--dataset harmix` defaults `--mcp-batch-size` to `1` and `--judge-model` to
`claude-sonnet-4-5`. Results land in the `harmix_mcp_results` Mongo collection.

## License

The persona data is internal Harmix content and is **not** an open dataset. Only the
machine-readable `harmix_bench_cases.json` is committed; per-persona memory snapshots are
kept in GCS and are not redistributed here.
