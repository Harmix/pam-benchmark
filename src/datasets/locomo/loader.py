"""LoCoMo dataset loader — reads `data/locomo10.json`."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from datasets.locomo.schemas import LoCoMoSample

DEFAULT_DATA_PATH = Path(__file__).parent / "data" / "locomo10.json"


class LoCoMoLoader:
    """Custom JSON loader for the LoCoMo dataset.

    We avoid HF `datasets` because its top-level import name collides with
    our `src/datasets/` package. The file is small (~3 MB) so an eager
    in-memory load is fine.
    """

    name = "locomo"
    version = "1.0"

    def __init__(self, data_path: Path | str | None = None):
        self._data_path = Path(data_path) if data_path else DEFAULT_DATA_PATH
        if not self._data_path.exists():
            raise FileNotFoundError(
                f"LoCoMo data file not found at {self._data_path}. "
                "Run `python scripts/download_data.py --dataset locomo` "
                "or place locomo10.json at the expected path."
            )
        with self._data_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        self._samples: list[LoCoMoSample] = [LoCoMoSample.model_validate(item) for item in raw]

    def num_samples(self) -> int:
        return len(self._samples)

    def get_sample(self, index: int) -> LoCoMoSample:
        if not 0 <= index < len(self._samples):
            raise IndexError(
                f"sample index {index} out of range (0..{len(self._samples) - 1})"
            )
        return self._samples[index]

    def iter_samples(self) -> Iterator[LoCoMoSample]:
        yield from self._samples

    def data_path(self) -> Path:
        return self._data_path
