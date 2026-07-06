"""Harmix dataset loader — reads `data/harmix_bench_cases.json`.

One benchmark *sample* per environment (persona); the sample's `qa` are that
environment's cases from `cases["<env_id>_cases"]`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from datasets.harmix.schemas import HarmixCase, HarmixEnvironment, HarmixSample

DEFAULT_DATA_PATH = Path(__file__).parent / "data" / "harmix_bench_cases.json"


class HarmixLoader:
    """Custom JSON loader for the Harmix golden-persona bench.

    The file is tiny (~40 KB) so an eager in-memory load is fine. Samples are
    ordered by the `environments` array; each sample bundles the environment
    with the cases from `cases["<env_id>_cases"]`.
    """

    name = "harmix"
    version = "1.0"

    def __init__(self, data_path: Path | str | None = None):
        self._data_path = Path(data_path) if data_path else DEFAULT_DATA_PATH
        if not self._data_path.exists():
            raise FileNotFoundError(
                f"Harmix data file not found at {self._data_path}. "
                "Run `python scripts/download_data.py --dataset harmix` "
                "or place harmix_bench_cases.json at the expected path."
            )
        with self._data_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)

        cases_by_env: dict[str, list] = raw.get("cases", {})
        self._samples: list[HarmixSample] = []
        for env_raw in raw.get("environments", []):
            env = HarmixEnvironment.model_validate(env_raw)
            case_items = cases_by_env.get(f"{env.id}_cases", [])
            cases = [HarmixCase.model_validate(c) for c in case_items]
            self._samples.append(HarmixSample(environment=env, cases=cases))

    def num_samples(self) -> int:
        return len(self._samples)

    def get_sample(self, index: int) -> HarmixSample:
        if not 0 <= index < len(self._samples):
            raise IndexError(f"sample index {index} out of range (0..{len(self._samples) - 1})")
        return self._samples[index]

    def index_for_sample_id(self, sample_id: str) -> int:
        for i, s in enumerate(self._samples):
            if s.sample_id == sample_id:
                return i
        available = [s.sample_id for s in self._samples]
        raise ValueError(f"unknown Harmix environment id: {sample_id!r}. Available: {available}")

    def iter_samples(self) -> Iterator[HarmixSample]:
        yield from self._samples

    def data_path(self) -> Path:
        return self._data_path
