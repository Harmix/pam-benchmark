"""Dataset loader protocol — every dataset implements this.

Per-dataset modules under `datasets/<name>/` provide a concrete loader. The
runner accesses them through the `DatasetLoader` protocol and never imports
dataset-specific types directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DatasetLoader(Protocol):
    """Iterate samples of a memory dataset.

    Loaders return dataset-specific pydantic models — the runner treats them
    as opaque values and only the matching task knows their shape.
    """

    name: str
    version: str

    def num_samples(self) -> int: ...

    def get_sample(self, index: int) -> Any: ...

    def iter_samples(self) -> Iterator[Any]: ...

    def data_path(self) -> Path: ...
