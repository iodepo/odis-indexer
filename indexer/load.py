"""Orchestrate S3 read → facade extract → Elasticsearch bulk load."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from datetime import datetime
from .config import AppConfig, graph_iri, index_name
from .elasticsearch_client import build_client, bulk_index, replace_index
from .extract import documents_from_jsonld_bytes
from .reader import build_minio_client, harvest_url_from_metadata, iter_jsonld_objects
from .resolver import Resolver

logger = logging.getLogger(__name__)


@dataclass
class LoadStats:
    source: str
    index: str
    objects_seen: int = 0
    documents: int = 0
    indexed: int = 0
    bulk_errors: int = 0
    dry_run: bool = False
    errors: int = 0
    messages: list[str] = field(default_factory=list)
    summoner_stats: dict = field(default_factory=dict)

    def summary(self) -> str:
        state = "dry-run" if self.dry_run else ("indexed" if self.indexed else "not-indexed")
        return (
            f"source={self.source} index={self.index} objects={self.objects_seen} "
            f"documents={self.documents} indexed={self.indexed} "
            f"status={state} errors={self.errors} bulk_errors={self.bulk_errors}"
        )


def run_load(
    cfg: AppConfig,
    source: str,
    *,
    limit: int | None = None,
    dry_run: bool = False,
) -> LoadStats:
    source = source.strip()
    idx = index_name(source, cfg.search.index_prefix)
    g_iri = graph_iri(source)
    stats = LoadStats(source=source, index=idx, dry_run=dry_run)

    s3 = build_minio_client(cfg.objectstore)
    bucket = cfg.objectstore.bucket

    resolver = Resolver(cfg.triplestore.endpoint if cfg.triplestore else None)

    docs: list[dict] = []
    try:
        for key, body, meta in iter_jsonld_objects(s3, bucket, source, limit=limit):
            stats.objects_seen += 1
            source_url = harvest_url_from_metadata(meta)
            extracted = documents_from_jsonld_bytes(
                body,
                source=source,
                s3_key=key,
                graph=g_iri,
                source_url=source_url,
                resolver=resolver,
            )
            if not extracted:
                stats.errors += 1
                logger.warning("No documents from %s", key)
                continue
            docs.extend(extracted)
            logger.info(
                "Extracted %d document(s) from %s (source_url=%s)",
                len(extracted),
                key,
                source_url or "—",
            )
    finally:
        resolver.close()

    stats.documents = len(docs)

    if stats.objects_seen == 0:
        stats.messages.append(f"no objects under summoned/{source}/")
        logger.warning(stats.messages[-1])
        # Even if 0 objects, we should try to update stats (e.g. if summoner failed)
        es = build_client(cfg.search.base_endpoint)
        try:
            stats_key = f"summoned/{source}/stats.json"
            if s3.bucket_exists(bucket):
                stats_bytes = s3.get_object(bucket, stats_key).read()
                stats.summoner_stats = json.loads(stats_bytes)
                logger.info("Loaded summoner stats for %s (0 objects)", source)
        except Exception as exc:
            logger.debug("No summoner stats found for %s (0 objects): %s", source, exc)
        update_odiscat_stats(es, stats)
        return stats

    if dry_run:
        logger.info(
            "[dry-run] would replace index %s and bulk %d document(s)",
            idx,
            stats.documents,
        )
        for d in docs[:3]:
            logger.info(
                "[dry-run] sample id=%s name=%s type=%s",
                d.get("_id"),
                d.get("name"),
                d.get("type"),
            )
        return stats

    if not docs:
        stats.messages.append("nothing to index after extraction")
        logger.error(stats.messages[-1])
        es = build_client(cfg.search.base_endpoint)
        # Try to load summoner stats even if no docs extracted
        try:
            stats_key = f"summoned/{source}/stats.json"
            if s3.bucket_exists(bucket):
                stats_bytes = s3.get_object(bucket, stats_key).read()
                stats.summoner_stats = json.loads(stats_bytes)
                logger.info("Loaded summoner stats for %s (no docs)", source)
        except Exception as exc:
            logger.debug("No summoner stats found for %s (no docs): %s", source, exc)
        update_odiscat_stats(es, stats)
        return stats

    es = build_client(cfg.search.base_endpoint)
    
    # Try to load summoner stats
    try:
        stats_key = f"summoned/{source}/stats.json"
        if s3.bucket_exists(bucket):
            stats_bytes = s3.get_object(bucket, stats_key).read()
            stats.summoner_stats = json.loads(stats_bytes)
            logger.info("Loaded summoner stats for %s", source)
    except Exception as exc:
        logger.debug("No summoner stats found for %s: %s", source, exc)

    # shallow copy docs so bulk can pop _id without mutating if re-run in process
    payload = [dict(d) for d in docs]
    replace_index(es, idx, source)
    success, bulk_errors = bulk_index(es, idx, payload)
    stats.indexed = success
    if bulk_errors:
        stats.messages.extend(bulk_errors)
    # refresh for immediate searchability in demos
    es.indices.refresh(index=idx)
    logger.info("Indexed %s documents into %s", success, idx)

    update_odiscat_stats(es, stats)

    return stats


def update_odiscat_stats(client: Elasticsearch, stats: LoadStats) -> None:
    """Update the odiscat index with stats from the latest indexer run."""
    index_name = "odiscat"
    if not client.indices.exists(index=index_name):
        logger.warning("Index %s does not exist, skipping stats update", index_name)
        return

    doc = {
        "doc": {
            "last_indexed": datetime.utcnow().isoformat(),
            "indexed_objects_seen": stats.objects_seen,
            "indexed_count": stats.indexed,
            "indexed_errors": stats.errors + len([m for m in stats.messages if "ID " in m]),
            "indexed_error_messages": stats.messages,
            # Reset summoner fields if no summoner stats provided, or they will be overwritten below
            "summoner_pages_seen": 0,
            "summoner_extracted": 0,
            "summoner_stored": 0,
            "summoner_errors": 0,
            "summoner_messages": [],
        }
    }
    
    # Merge summoner stats if present
    if stats.summoner_stats:
        s_stats = stats.summoner_stats
        doc["doc"].update({
            "summoner_pages_seen": s_stats.get("pages_seen", 0),
            "summoner_extracted": s_stats.get("extracted", 0),
            "summoner_stored": s_stats.get("stored", 0),
            "summoner_errors": s_stats.get("errors", 0),
            "summoner_messages": s_stats.get("messages", []),
        })
        # If there are summoner errors, make sure they are reflected or added to error count if needed
        # For now we just add them as separate fields.
    
    try:
        client.update(index=index_name, id=stats.source, body=doc, retry_on_conflict=3)
        logger.info("Updated %s stats for source %s", index_name, stats.source)
    except Exception as exc:
        logger.error("Failed to update %s for %s: %s", index_name, stats.source, exc)
