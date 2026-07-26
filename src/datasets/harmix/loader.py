"""Harmix dataset loader — reads `harmix_bench_cases.json` from GCS.

One benchmark *sample* per environment (persona); the sample's `qa` are that
environment's cases from `cases["<env_id>_cases"]`.

The bench-cases JSON lives **only** in GCS
(``gs://pam-dev-memory-data/benchmark/datasets/harmix/harmix_bench_cases.json``,
alongside the per-persona memory-snapshot zips) and is read straight into memory
via the google-cloud-storage client — it is never read from local disk. Point at
a different object with an explicit ``gs://`` source or ``HARMIX_BENCH_CASES_URI``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

from datasets.harmix.schemas import HarmixCase, HarmixEnvironment, HarmixSample

logger = logging.getLogger(__name__)

# Source of truth: the bench-cases JSON in GCS, next to the memory-snapshot zips.
DEFAULT_DATA_URI = "gs://pam-dev-memory-data/benchmark/datasets/harmix/harmix_bench_cases.json"
# Env var to override the source (must be a gs:// URI).
DATA_URI_ENV = "HARMIX_BENCH_CASES_URI"


def _read_gcs_bytes(gs_uri: str) -> bytes:
    """Read a `gs://bucket/key` object's contents into memory (no local file)."""
    without_scheme = gs_uri[len("gs://") :]
    bucket_name, _, blob_name = without_scheme.partition("/")
    try:
        # Prefer the GCS SDK; stream the object straight into memory.
        from google.cloud import storage  # type: ignore

        return storage.Client().bucket(bucket_name).blob(blob_name).download_as_bytes()
    except ImportError:
        # Fall back to the gcloud CLI, capturing stdout (still no local file).
        proc = subprocess.run(["gcloud", "storage", "cat", gs_uri], check=True, capture_output=True)
        return proc.stdout


def _load_raw(source: str | None) -> tuple[str, dict]:
    """Load the bench-cases JSON from GCS, returning ``(uri, parsed)``.

    Source priority: explicit ``source`` → ``HARMIX_BENCH_CASES_URI`` → ``DEFAULT_DATA_URI``.
    The source must be a ``gs://`` URI — the cases are never read from local disk.
    """
    uri = source if source is not None else os.environ.get(DATA_URI_ENV, DEFAULT_DATA_URI)
    if not uri.startswith("gs://"):
        raise ValueError(
            f"Harmix bench cases must be a gs:// URI, got {uri!r}. "
            f"Leave the source unset for the default ({DEFAULT_DATA_URI}) or set "
            f"${DATA_URI_ENV} to a gs:// URI."
        )
    logger.info("Reading Harmix bench cases from %s", uri)
    return uri, json.loads(_read_gcs_bytes(uri))


class HarmixLoader:
    """Custom JSON loader for the Harmix golden-persona bench.

    The file is tiny (~40 KB) so an eager in-memory load is fine. It is read from
    GCS (:data:`DEFAULT_DATA_URI`) straight into memory — never from local disk;
    pass a ``gs://`` URI, or set ``HARMIX_BENCH_CASES_URI``, to point elsewhere.
    Samples are ordered by the `environments` array; each sample bundles the
    environment with the cases from `cases["<env_id>_cases"]`.
    """

    name = "harmix"
    version = "1.0"

    def __init__(self, source: str | None = None):
        self._source, raw = _load_raw(source)

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

    def data_path(self) -> Path | None:
        """Always ``None`` — the cases live in GCS, not on local disk (see :meth:`source`)."""
        return None

    def source(self) -> str:
        """The ``gs://`` URI the cases were read from."""
        return self._source
