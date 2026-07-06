"""Pydantic schemas for the Harmix golden-persona bench.

Mirrors `data/harmix_bench_cases.json`. Each **environment** (persona) is one
benchmark *sample* (the LoCoMo "conversation" analogue); its cases are the
sample's questions. Memory for a sample is built from the environment's
pre-staged GCS `memory_snapshot` (a `state_after_sources_download.zip`) rather
than an uploaded conversation file.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# memory_sources tokens (dataset) → memory-pipeline extract handler keys
# (pam-jobs `extract.py::ALL_SOURCES`). Unknown tokens pass through unchanged.
SOURCE_NAME_MAP: dict[str, str] = {
    "emails": "gmail",
    "email": "gmail",
    "meetings": "meeting_transcripts",
    "meeting_transcripts": "meeting_transcripts",
}


def map_sources(memory_sources: list[str]) -> list[str]:
    """Map dataset `memory_sources` tokens to pipeline `--sources` keys.

    Preserves order, drops duplicates, and passes unknown tokens through.
    """
    seen: set[str] = set()
    out: list[str] = []
    for src in memory_sources:
        mapped = SOURCE_NAME_MAP.get(src, src)
        if mapped not in seen:
            seen.add(mapped)
            out.append(mapped)
    return out


class HarmixCase(BaseModel):
    """One question asked against an environment's fixed memory state."""

    model_config = ConfigDict(extra="ignore")

    id: str
    environment: str
    source_id: int | None = None
    question: str
    context: list[str] = []
    # Gold/reference answer. `None` for open/draft tasks with no single gold.
    expected_answer: str | None = None
    # Extra grading guidance / checklist criteria; `None` if none.
    grading_notes: str | None = None

    # ---- LoCoMo-compat shims so the shared machinery treats a case like a QA ---
    @property
    def answer(self) -> str:
        return self.expected_answer or ""

    @property
    def category(self) -> int:
        return 0  # Harmix has no LoCoMo-style categories.

    @property
    def category_name(self) -> str:
        return "harmix"

    @property
    def evidence(self) -> list[str]:
        return []


class HarmixEnvironment(BaseModel):
    """A persona's fixed memory state and where to build it from."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    role: str | None = None
    aliases: list[str] = []
    memory_sources: list[str]
    description: str | None = None
    source_file: str | None = None
    # gs:// URI of the pre-staged state_after_sources_download.zip snapshot.
    memory_snapshot: str


class HarmixSample(BaseModel):
    """One environment + its cases — the runner's unit of work.

    Exposes `sample_id` / `qa` so the shared task/runner code can treat it like
    a LoCoMo sample, plus `memory_snapshot` / `pipeline_sources` for the
    snapshot-based memory build.
    """

    model_config = ConfigDict(extra="ignore")

    environment: HarmixEnvironment
    cases: list[HarmixCase]

    @property
    def sample_id(self) -> str:
        return self.environment.id

    @property
    def qa(self) -> list[HarmixCase]:
        return self.cases

    @property
    def memory_snapshot(self) -> str:
        return self.environment.memory_snapshot

    @property
    def memory_sources(self) -> list[str]:
        return self.environment.memory_sources

    @property
    def pipeline_sources(self) -> list[str]:
        """`memory_sources` mapped to pipeline `--sources` keys."""
        return map_sources(self.environment.memory_sources)
