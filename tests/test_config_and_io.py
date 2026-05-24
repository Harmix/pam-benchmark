"""RunConfig and shared IO helpers — both used by every script."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from config import RunConfig
from utils.io import read_json, sha256, write_json
from utils.timing import timed


def test_runconfig_minimal_valid():
    cfg = RunConfig(exp_name="x", dataset="locomo", baseline="gpt-4-turbo")
    assert cfg.seed == 42
    assert cfg.judge_model == "gpt-4o"
    assert cfg.resolved_task() == "locomo"
    assert cfg.resolved_output_dir() == Path("outputs") / "x" / "42"


def test_runconfig_task_override():
    cfg = RunConfig(exp_name="x", dataset="locomo", task="custom", baseline="b")
    assert cfg.resolved_task() == "custom"


def test_runconfig_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        RunConfig(exp_name="x", dataset="locomo", baseline="b", unknown_field="boom")


def test_runconfig_baseline_kwargs_must_be_dict():
    with pytest.raises(ValidationError):
        RunConfig(exp_name="x", dataset="locomo", baseline="b", baseline_kwargs="not a dict")


def test_write_then_read_json_roundtrip(tmp_path: Path):
    data = {"a": 1, "nested": [1, 2, {"k": "v"}]}
    p = tmp_path / "sub" / "x.json"
    write_json(p, data)
    assert p.exists()
    assert read_json(p) == data


def test_write_json_handles_non_serializable_via_default(tmp_path: Path):
    # write_json uses default=str — sets become strings, Path becomes str, etc.
    p = tmp_path / "x.json"
    write_json(p, {"path": Path("/tmp"), "values": (1, 2, 3)})
    obj = json.loads(p.read_text())
    assert obj["path"] == "/tmp"
    assert obj["values"] == [1, 2, 3]  # tuples → lists


def test_sha256_deterministic(tmp_path: Path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello world")
    h1 = sha256(p)
    h2 = sha256(p)
    assert h1 == h2
    assert len(h1) == 64  # hex


def test_sha256_changes_with_content(tmp_path: Path):
    p1 = tmp_path / "a.bin"
    p2 = tmp_path / "b.bin"
    p1.write_bytes(b"hello world")
    p2.write_bytes(b"hello world!")
    assert sha256(p1) != sha256(p2)


def test_timed_records_seconds():
    import time

    with timed() as t:
        time.sleep(0.01)
    assert t.seconds >= 0.01
    assert t.ms >= 10.0
