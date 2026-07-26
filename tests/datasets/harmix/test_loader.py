"""Harmix loader + source-mapping tests.

The loader reads its bench-cases JSON only from GCS; these tests stub the GCS
read (`_read_gcs_bytes`) with the shipped file's bytes so they run offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from datasets.harmix import loader as harmix_loader
from datasets.harmix.loader import HarmixLoader
from datasets.harmix.schemas import HarmixSample, map_sources

# The shipped bench-cases file, used only as fixture bytes for the mocked GCS read.
SHIPPED = Path(harmix_loader.__file__).parent / "data" / "harmix_bench_cases.json"


@pytest.fixture
def gcs_shipped(monkeypatch):
    """Serve the shipped bench-cases file as if it were the GCS object."""
    monkeypatch.setattr(harmix_loader, "_read_gcs_bytes", lambda uri: SHIPPED.read_bytes())


def test_source_mapping():
    assert map_sources(["emails", "meetings"]) == ["gmail", "meeting_transcripts"]
    assert map_sources(["emails"]) == ["gmail"]
    # de-dupes and preserves order; unknown tokens pass through.
    assert map_sources(["emails", "email", "slack"]) == ["gmail", "slack"]


def test_default_source_reads_from_gcs(monkeypatch):
    """No-arg construction reads the default GCS URI into memory via `_read_gcs_bytes`."""
    calls: list[str] = []

    def fake_read(uri: str) -> bytes:
        calls.append(uri)
        return SHIPPED.read_bytes()

    monkeypatch.setattr(harmix_loader, "_read_gcs_bytes", fake_read)
    ld = HarmixLoader()
    assert calls == [harmix_loader.DEFAULT_DATA_URI]
    assert ld.source() == harmix_loader.DEFAULT_DATA_URI
    assert ld.data_path() is None  # cases live in GCS, never on local disk
    assert ld.num_samples() == 4


def test_env_var_overrides_source(monkeypatch):
    monkeypatch.setenv(harmix_loader.DATA_URI_ENV, "gs://bucket/custom.json")
    monkeypatch.setattr(harmix_loader, "_read_gcs_bytes", lambda uri: SHIPPED.read_bytes())
    ld = HarmixLoader()
    assert ld.source() == "gs://bucket/custom.json"
    assert ld.num_samples() == 4


def test_rejects_non_gcs_source():
    with pytest.raises(ValueError, match="gs://"):
        HarmixLoader("/tmp/local.json")


def test_loader_reads_shipped_cases(gcs_shipped):
    ld = HarmixLoader()
    assert ld.num_samples() == 4
    ids = [ld.get_sample(i).sample_id for i in range(ld.num_samples())]
    assert ids == ["nazar", "oleksandr", "nick", "nazar_mini"]

    oleksandr = ld.get_sample(ld.index_for_sample_id("oleksandr"))
    assert isinstance(oleksandr, HarmixSample)
    assert oleksandr.memory_sources == ["emails"]
    assert oleksandr.pipeline_sources == ["gmail"]
    assert oleksandr.memory_snapshot.startswith("gs://")
    assert len(oleksandr.qa) == 20
    # Open/draft tasks (e.g. the Paul Ziperski reply draft) keep a null gold answer.
    nulls = [c.id for c in oleksandr.qa if c.expected_answer is None]
    assert "oleksandr-18" in nulls


def test_loader_reads_nazar_mini_environment(gcs_shipped):
    ld = HarmixLoader()
    mini = ld.get_sample(ld.index_for_sample_id("nazar_mini"))
    assert mini.memory_sources == ["emails", "meetings"]
    assert mini.pipeline_sources == ["gmail", "meeting_transcripts"]
    assert mini.memory_snapshot.startswith("gs://")
    # Carries nazar's first 11 questions, re-ided under its own environment.
    nazar = ld.get_sample(ld.index_for_sample_id("nazar"))
    assert [c.question for c in mini.qa] == [c.question for c in nazar.qa[: len(mini.qa)]]
    assert all(c.id.startswith("nazar_mini-") for c in mini.qa)


def test_index_for_unknown_id_raises(gcs_shipped):
    ld = HarmixLoader()
    with pytest.raises(ValueError, match="unknown Harmix environment id"):
        ld.index_for_sample_id("nobody")


def test_case_locomo_compat_shims(gcs_shipped):
    ld = HarmixLoader()
    case = ld.get_sample(0).qa[0]
    assert case.category == 0
    assert case.category_name == "harmix"
    assert case.evidence == []
    assert case.answer == (case.expected_answer or "")


def test_loader_from_custom_source(monkeypatch):
    payload = {
        "environments": [
            {
                "id": "solo",
                "name": "Solo",
                "memory_sources": ["emails"],
                "memory_snapshot": "gs://bucket/solo.zip",
            }
        ],
        "cases": {
            "solo_cases": [
                {"id": "solo-1", "environment": "solo", "question": "hi?", "expected_answer": "yo"}
            ]
        },
    }
    monkeypatch.setattr(
        harmix_loader, "_read_gcs_bytes", lambda uri: json.dumps(payload).encode("utf-8")
    )
    ld = HarmixLoader("gs://bucket/cases.json")
    assert ld.source() == "gs://bucket/cases.json"
    assert ld.num_samples() == 1
    s = ld.get_sample(0)
    assert s.sample_id == "solo"
    assert s.pipeline_sources == ["gmail"]
    assert len(s.qa) == 1
