"""Read per-message agent token metrics from Pam's Postgres DB.

After Pam answers a prompt, the agent writes one `pam.message_metrics` row with
the underlying model's token usage. The benchmark reads the most-recent row for
the acting user to surface those `agent_*` token counts alongside the rest of
the run. Connection details come from the same `DATABASE_*` env vars the memory
pipeline uses; the reader degrades gracefully (returns nothing) when they are
absent or the DB is unreachable, so a run without DB access still completes.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# Most-recent metrics row for a user. `id`/`created_at` order identifies the row
# tied to the just-finished prompt.
_LATEST_METRICS_SQL = (
    "SELECT id, input_tokens, output_tokens, model_used, cache_read_tokens, "
    "cache_write_tokens, enriched_user_prompt_tokens "
    "FROM pam.message_metrics WHERE user_id = $1 "
    "ORDER BY created_at DESC LIMIT 1"
)

_CONNECT_TIMEOUT_SEC = 10.0


@dataclass
class AgentMetrics:
    """One `pam.message_metrics` row, renamed for the benchmark."""

    metrics_id: Any
    agent_input_tokens: int
    agent_output_tokens: int
    agent_model_used: str | None
    agent_cache_read_tokens: int
    agent_cache_write_tokens: int
    enriched_user_prompt_tokens: int


class PamMetricsReader:
    """Lazily-pooled reader for `pam.message_metrics`.

    The asyncpg pool is created on first use (so it binds to the running event
    loop) and reused across batches. Any connection/query failure disables the
    reader for the rest of the run and is surfaced once as a warning — the
    caller then treats the `agent_*` counts as 0.
    """

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None
        self._disabled = False

    async def _pool_or_none(self) -> asyncpg.Pool | None:
        if self._disabled:
            return None
        if self._pool is None:
            try:
                self._pool = await asyncpg.create_pool(
                    host=os.environ["DATABASE_HOST"],
                    port=int(os.environ.get("DATABASE_PORT") or 5432),
                    user=os.environ["DATABASE_USERNAME"],
                    password=os.environ["DATABASE_PASSWORD"],
                    database=os.environ["DATABASE_NAME"],
                    min_size=1,
                    max_size=2,
                    timeout=_CONNECT_TIMEOUT_SEC,
                )
            except Exception as e:
                logger.warning("Pam metrics DB unavailable (%r); agent_* token counts will be 0", e)
                self._disabled = True
                return None
        return self._pool

    async def latest_for_user(self, user_id: int | None) -> AgentMetrics | None:
        """Return the most-recent metrics row for `user_id`, or None."""
        if user_id is None:
            return None
        pool = await self._pool_or_none()
        if pool is None:
            return None
        try:
            row = await pool.fetchrow(_LATEST_METRICS_SQL, user_id)
        except Exception as e:
            logger.warning("Pam metrics query failed for user_id=%s: %r", user_id, e)
            return None
        if row is None:
            return None
        return AgentMetrics(
            metrics_id=row["id"],
            agent_input_tokens=row["input_tokens"] or 0,
            agent_output_tokens=row["output_tokens"] or 0,
            agent_model_used=row["model_used"],
            agent_cache_read_tokens=row["cache_read_tokens"] or 0,
            agent_cache_write_tokens=row["cache_write_tokens"] or 0,
            enriched_user_prompt_tokens=row["enriched_user_prompt_tokens"] or 0,
        )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
