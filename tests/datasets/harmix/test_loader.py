"""Harmix loader + source-mapping tests (uses the shipped bench-cases JSON)."""

from __future__ import annotations

import json

import pytest

from datasets.harmix.loader import HarmixLoader
from datasets.harmix.schemas import HarmixSample, map_sources


def test_source_mapping():
    assert map_sources(["emails", "meetings"]) == ["gmail", "meeting_transcripts"]
    assert map_sources(["emails"]) == ["gmail"]
    # de-dupes and preserves order; unknown tokens pass through.
    assert map_sources(["emails", "email", "slack"]) == ["gmail", "slack"]


def test_loader_reads_shipped_cases():
    ld = HarmixLoader()
    assert ld.num_samples() == 3
    ids = [ld.get_sample(i).sample_id for i in range(ld.num_samples())]
    assert ids == ["nazar", "oleksandr", "nick"]

    oleksandr = ld.get_sample(ld.index_for_sample_id("oleksandr"))
    assert isinstance(oleksandr, HarmixSample)
    assert oleksandr.memory_sources == ["emails"]
    assert oleksandr.pipeline_sources == ["gmail"]
    assert oleksandr.memory_snapshot.startswith("gs://")
    assert len(oleksandr.qa) == 21
    # Open/draft tasks keep a null gold answer.
    nulls = [c.id for c in oleksandr.qa if c.expected_answer is None]
    assert "oleksandr-17" in nulls and "oleksandr-19" in nulls


def test_index_for_unknown_id_raises():
    ld = HarmixLoader()
    with pytest.raises(ValueError, match="unknown Harmix environment id"):
        ld.index_for_sample_id("nobody")


def test_case_locomo_compat_shims():
    ld = HarmixLoader()
    case = ld.get_sample(0).qa[0]
    assert case.category == 0
    assert case.category_name == "harmix"
    assert case.evidence == []
    assert case.answer == (case.expected_answer or "")


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        HarmixLoader(tmp_path / "nope.json")


def test_loader_from_custom_path(tmp_path):
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
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    ld = HarmixLoader(path)
    assert ld.num_samples() == 1
    s = ld.get_sample(0)
    assert s.sample_id == "solo"
    assert s.pipeline_sources == ["gmail"]
    assert len(s.qa) == 1
