"""MongoDB writer.

One document per `(exp_name, sample_id, seed)` in the per-dataset collection
(`locomo_results` for LoCoMo). The full per-question payload lives in the
`qa_responses` nested array — replaces the legacy `incorrect_responses` field.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from pymongo import MongoClient

logger = logging.getLogger(__name__)


def collection_for(dataset: str) -> str:
    """`<dataset>_results` — keeps existing dashboards working."""
    return f"{dataset}_results"


def _get_client(connection_string: str) -> MongoClient:
    return MongoClient(connection_string, serverSelectionTimeoutMS=5000)


def write_sample_result(
    *,
    dataset: str,
    document: dict[str, Any],
    connection_string: str | None = None,
    db_name: str | None = None,
    collection: str | None = None,
) -> str | None:
    """Insert one sample document. Returns the inserted_id or None on failure.

    `collection` overrides the default `<dataset>_results` (e.g. MCP-on-harness
    runs write to `<dataset>_mcp_results`).
    """
    cs = connection_string or os.environ.get("CONNECTION_STRING")
    db = db_name or os.environ.get("DB_NAME")
    if not cs or not db:
        logger.warning(
            "MongoDB not configured (CONNECTION_STRING/DB_NAME missing); skipping write."
        )
        return None

    coll_name = collection or collection_for(dataset)

    ts = datetime.now(UTC)
    document = {
        **document,
        "timestamp": ts,
        "created_at": ts.isoformat(),
    }

    try:
        client = _get_client(cs)
        client.admin.command("ping")
        result = client[db][coll_name].insert_one(document)
        client.close()
        logger.info(
            "Mongo write OK: db=%s coll=%s _id=%s exp=%s sample=%s",
            db,
            coll_name,
            result.inserted_id,
            document.get("exp_name"),
            document.get("sample_id"),
        )
        return str(result.inserted_id)
    except Exception as e:
        logger.warning("Mongo write FAILED: %s", e)
        return None
