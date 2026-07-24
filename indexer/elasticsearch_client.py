"""Elasticsearch index management and bulk load."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from elasticsearch import Elasticsearch, helpers

logger = logging.getLogger(__name__)

INDEX_BODY: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "dynamic": True,
        "properties": {
            "source": {"type": "keyword"},
            "s3_key": {"type": "keyword"},
            "graph": {"type": "keyword"},
            "id": {"type": "keyword"},
            "type": {"type": "keyword"},
            "name": {
                "type": "text",
                "fields": {"raw": {"type": "keyword", "ignore_above": 512}},
            },
            "description": {"type": "text"},
            "keywords": {
                "type": "text",
                "fields": {"raw": {"type": "keyword"}},
            },
            "url": {"type": "keyword", "ignore_above": 2048},
            "source_url": {"type": "keyword", "ignore_above": 2048},
            "jsonld": {"type": "object", "enabled": False},
        },
    },
}


def build_client(endpoint: str) -> Elasticsearch:
    return Elasticsearch(endpoint.rstrip("/"))


def replace_index(client: Elasticsearch, index: str, source: str) -> None:
    """Ensure index exists, and remove existing documents for this source."""
    if not client.indices.exists(index=index):
        logger.info("Creating index %s", index)
        client.indices.create(
            index=index,
            settings=INDEX_BODY["settings"],
            mappings=INDEX_BODY["mappings"],
        )
        return

    # If index exists, delete documents for this source
    # s3_key typically looks like 'summoned/{source}/...'
    query = {"prefix": {"s3_key": f"summoned/{source}/"}}
    logger.info("Removing existing documents for source '%s' in %s", source, index)
    res = client.delete_by_query(
        index=index,
        query=query,
        refresh=True,
    )
    logger.info("Removed %s documents", res.get("deleted", 0))


def bulk_index(
    client: Elasticsearch,
    index: str,
    documents: Iterable[dict[str, Any]],
) -> tuple[int, int]:
    """Bulk index documents. Returns (success_count, error_count)."""

    def actions() -> Iterable[dict[str, Any]]:
        for doc in documents:
            doc_id = doc.pop("_id", None)
            action: dict[str, Any] = {
                "_index": index,
                "_source": doc,
            }
            if doc_id:
                action["_id"] = doc_id
            yield action

    success, errors = helpers.bulk(
        client,
        actions(),
        raise_on_error=False,
        raise_on_exception=False,
    )
    err_count = len(errors) if isinstance(errors, list) else int(errors or 0)
    logger.info("Bulk index %s: success=%s errors=%s", index, success, err_count)
    if err_count and isinstance(errors, list):
        for err in errors[:5]:
            logger.warning("Bulk error sample: %s", err)
    return int(success), err_count
