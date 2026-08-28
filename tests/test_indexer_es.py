from __future__ import annotations

from unittest.mock import MagicMock, patch

from indexer.elasticsearch_client import bulk_index, bulk_update, replace_index
from indexer.load import LoadStats, update_odiscat_stats


def test_replace_index_uses_delete_by_query_if_exists() -> None:
    client = MagicMock()
    client.indices.exists.return_value = True
    replace_index(client, "odis", "oceanexpert")
    client.delete_by_query.assert_called_once()
    kwargs = client.delete_by_query.call_args.kwargs
    assert kwargs["index"] == "odis"
    assert kwargs["query"]["prefix"]["s3_key"] == "summoned/oceanexpert/"
    # Should NOT delete index if it exists
    client.indices.delete.assert_not_called()


def test_replace_index_creates_if_missing() -> None:
    client = MagicMock()
    client.indices.exists.return_value = False
    replace_index(client, "odis", "oceanexpert")
    client.indices.create.assert_called_once()
    kwargs = client.indices.create.call_args.kwargs
    assert kwargs["index"] == "odis"
    # Should NOT call delete_by_query if index was just created
    client.delete_by_query.assert_not_called()


def test_bulk_index_pops_id() -> None:
    client = MagicMock()
    docs = [
        {
            "_id": "https://example.org/1",
            "name": "A",
            "source": "medin",
        }
    ]
    with patch("indexer.elasticsearch_client.helpers.bulk") as bulk:
        bulk.return_value = (1, [])
        success, errors = bulk_index(client, "odis", docs)
    assert success == 1
    assert errors == []
    actions = list(bulk.call_args[0][1])
    assert actions[0]["_id"] == "https://example.org/1"
    assert actions[0]["_source"]["name"] == "A"
    assert "_id" not in actions[0]["_source"]


def test_bulk_update_actions() -> None:
    client = MagicMock()
    docs = [
        {
            "_id": "medin",
            "sourceid": "medin",
            "name": "MEDIN",
        }
    ]
    with patch("indexer.elasticsearch_client.helpers.bulk") as bulk:
        bulk.return_value = (1, [])
        success, errors = bulk_update(client, "odiscat", docs, doc_as_upsert=True)
    assert success == 1
    assert errors == []
    actions = list(bulk.call_args[0][1])
    assert actions[0]["_op_type"] == "update"
    assert actions[0]["_index"] == "odiscat"
    assert actions[0]["_id"] == "medin"
    assert actions[0]["doc"]["sourceid"] == "medin"
    assert actions[0]["doc"]["name"] == "MEDIN"
    assert "_id" not in actions[0]["doc"]
    assert actions[0]["doc_as_upsert"] is True


def test_update_odiscat_stats_partial_update_without_summoner() -> None:
    client = MagicMock()
    client.indices.exists.return_value = True

    stats = LoadStats(
        source="medin",
        index="odis",
        objects_seen=10,
        indexed=10,
        errors=0,
        messages=[],
    )

    update_odiscat_stats(client, stats)

    client.index.assert_not_called()
    client.update.assert_called_once()
    kwargs = client.update.call_args.kwargs
    assert kwargs["index"] == "odiscat"
    assert kwargs["id"] == "medin"
    assert kwargs["doc_as_upsert"] is True
    doc = kwargs["doc"]
    assert doc["indexed_objects_seen"] == 10
    assert doc["indexed_count"] == 10
    assert doc["indexed_errors"] == 0
    assert "last_indexed" in doc
    # Summoner keys should NOT be present when summoner_stats is empty
    assert "summoner_pages_seen" not in doc
    assert "summoner_extracted" not in doc


def test_update_odiscat_stats_partial_update_with_summoner() -> None:
    client = MagicMock()
    client.indices.exists.return_value = True

    stats = LoadStats(
        source="medin",
        index="odis",
        objects_seen=10,
        indexed=10,
        errors=0,
        messages=[],
        summoner_stats={
            "pages_seen": 15,
            "extracted": 12,
            "stored": 10,
            "errors": 2,
            "messages": ["warn"],
        },
    )

    update_odiscat_stats(client, stats)

    client.index.assert_not_called()
    client.update.assert_called_once()
    kwargs = client.update.call_args.kwargs
    assert kwargs["index"] == "odiscat"
    assert kwargs["id"] == "medin"
    assert kwargs["doc_as_upsert"] is True
    doc = kwargs["doc"]
    assert doc["indexed_objects_seen"] == 10
    assert doc["summoner_pages_seen"] == 15
    assert doc["summoner_extracted"] == 12
    assert doc["summoner_stored"] == 10
    assert doc["summoner_errors"] == 2
    assert doc["summoner_messages"] == ["warn"]
