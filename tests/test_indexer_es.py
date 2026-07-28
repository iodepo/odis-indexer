from __future__ import annotations

from unittest.mock import MagicMock, patch

from indexer.elasticsearch_client import bulk_index, replace_index


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
