"""Shared fixtures for Pam baseline tests."""

from __future__ import annotations

import pytest

from baselines.pam.baseline import PamBaseline


@pytest.fixture(autouse=True)
def _no_inter_batch_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable the inter-batch sleep so batched-lifecycle tests run instantly."""
    monkeypatch.setattr(PamBaseline, "INTER_BATCH_SLEEP_SEC", 0.0)
