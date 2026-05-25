"""LoCoMo loader — verifies the on-disk shape stays compatible."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from datasets.base import DatasetLoader
from datasets.locomo.loader import LoCoMoLoader
from datasets.locomo.schemas import (
    CATEGORY_NAMES,
    LoCoMoQA,
    LoCoMoSample,
    LoCoMoTurn,
)


@pytest.fixture(scope="module")
def loader() -> LoCoMoLoader:
    return LoCoMoLoader()


def test_implements_protocol(loader):
    assert isinstance(loader, DatasetLoader)
    assert loader.name == "locomo"
    assert loader.version == "1.0"


def test_data_file_exists(loader):
    assert loader.data_path().exists()


def test_num_samples_positive(loader):
    assert loader.num_samples() > 0


def test_iter_samples_yields_validated_models(loader):
    samples = list(loader.iter_samples())
    assert len(samples) == loader.num_samples()
    assert all(isinstance(s, LoCoMoSample) for s in samples)


def test_get_sample_out_of_range_raises(loader):
    with pytest.raises(IndexError):
        loader.get_sample(loader.num_samples() + 100)


def test_each_qa_validates(loader):
    for s in loader.iter_samples():
        assert s.sample_id
        for qa in s.qa:
            assert isinstance(qa, LoCoMoQA)
            assert qa.category in CATEGORY_NAMES
            # Category 5 may have only adversarial_answer
            if qa.category != 5:
                assert qa.answer is not None or qa.adversarial_answer is not None


def test_int_answers_coerced_to_str(loader):
    # The raw JSON has integer answers in some rows; loader must coerce.
    for s in loader.iter_samples():
        for qa in s.qa:
            assert qa.answer is None or isinstance(qa.answer, str)
            assert qa.adversarial_answer is None or isinstance(qa.adversarial_answer, str)


def test_session_helpers(loader):
    s = loader.get_sample(0)
    indices = s.session_indices()
    assert indices == sorted(indices)
    assert indices  # at least one session
    first_session = s.session(indices[0])
    assert all(isinstance(t, LoCoMoTurn) for t in first_session)
    assert all(t.speaker and t.text and t.dia_id for t in first_session)
    assert s.session_date_time(indices[0])  # non-empty date string


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        LoCoMoLoader(data_path=tmp_path / "nonexistent.json")


def test_loader_accepts_custom_path(tmp_path: Path, loader):
    # Round-trip a single real sample through a custom path
    sample = loader.get_sample(0)
    custom = tmp_path / "tiny.json"
    custom.write_text(json.dumps([sample.model_dump()]), encoding="utf-8")
    other = LoCoMoLoader(data_path=custom)
    assert other.num_samples() == 1
    assert other.get_sample(0).sample_id == sample.sample_id


def test_category_names_complete():
    assert set(CATEGORY_NAMES) == {1, 2, 3, 4, 5}
