"""Rich-based progress helpers — one bar per sample, advanced per question."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)


@contextmanager
def progress_for(console: Console | None = None) -> Iterator[Progress]:
    """Yield a configured Rich `Progress` context."""
    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
        refresh_per_second=4,
    )
    with progress:
        yield progress


def add_sample_task(progress: Progress, sample_id: str, n: int) -> TaskID:
    return progress.add_task(f"sample {sample_id}", total=n)
