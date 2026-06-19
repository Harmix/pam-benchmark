"""Mongo query helpers for the report."""

from __future__ import annotations

import logging
import os
from typing import Any

from pymongo import MongoClient

logger = logging.getLogger(__name__)


def fetch_experiment(
    *,
    exp_name: str,
    dataset: str,
    connection_string: str | None = None,
    db_name: str | None = None,
    collection: str | None = None,
) -> list[dict[str, Any]]:
    """Return every Mongo document for `exp_name` in the dataset's collection.

    `collection` overrides the default `<dataset>_results` (e.g. pass
    `<dataset>_mcp_results` to report on MCP-on-harness experiments).
    """
    cs = connection_string or os.environ.get("CONNECTION_STRING")
    db = db_name or os.environ.get("DB_NAME")
    if not cs or not db:
        raise RuntimeError(
            "MongoDB not configured: set CONNECTION_STRING and DB_NAME in secrets.env"
        )
    coll_name = collection or f"{dataset}_results"
    client = MongoClient(cs, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    docs = list(
        client[db][coll_name].find({"exp_name": exp_name}).sort([("seed", 1), ("sample_index", 1)])
    )
    client.close()
    logger.info("Fetched %d docs for exp_name=%s coll=%s", len(docs), exp_name, coll_name)
    return docs
