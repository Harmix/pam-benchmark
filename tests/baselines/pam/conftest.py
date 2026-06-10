"""Shared fixtures for Pam baseline tests."""

from __future__ import annotations

import pytest

from baselines.pam.baseline import PamBaseline


@pytest.fixture(autouse=True)
def _no_pam_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable the inter-batch sleep and retry backoff so batched-lifecycle and
    retry tests run instantly."""
    monkeypatch.setattr(PamBaseline, "INTER_BATCH_SLEEP_SEC", 0.0)
    monkeypatch.setattr(PamBaseline, "BATCH_RETRY_BASE_SLEEP_SEC", 0.0)
