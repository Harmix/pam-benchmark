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
) -> list[dict[str, Any]]:
    """Return every Mongo document for `exp_name` in the dataset's collection."""
    cs = connection_string or os.environ.get("CONNECTION_STRING")
    db = db_name or os.environ.get("DB_NAME")
    if not cs or not db:
        raise RuntimeError(
            "MongoDB not configured: set CONNECTION_STRING and DB_NAME in secrets.env"
        )
    client = MongoClient(cs, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    docs = list(
        client[db][f"{dataset}_results"]
        .find({"exp_name": exp_name})
        .sort([("seed", 1), ("sample_index", 1)])
    )
    client.close()
    logger.info("Fetched %d docs for exp_name=%s dataset=%s", len(docs), exp_name, dataset)
    return docs
