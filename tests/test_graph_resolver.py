import logging
import pytest
from unittest.mock import MagicMock
from indexer.graph_resolver import resolve_links, _resolve_node

def test_resolve_node_basic():
    lookup = {
        "https://w3id.org/mbo_1": {
            "jsonld": {
                "@id": "https://w3id.org/mbo_1",
                "@type": "Place",
                "name": "Target Place",
                "geo": {"@type": "GeoCoordinates", "latitude": 10, "longitude": 20}
            }
        }
    }
    
    node = {
        "@id": "https://w3id.org/doc_1",
        "@type": "Dataset",
        "spatialCoverage": {"@id": "https://w3id.org/mbo_1"}
    }
    
    changed = _resolve_node(node, lookup)
    assert changed is True
    assert node["spatialCoverage"]["name"] == "Target Place"
    assert node["spatialCoverage"]["geo"]["latitude"] == 10

def test_resolve_node_list():
    lookup = {
        "id1": {"jsonld": {"@id": "id1", "name": "Name 1"}},
        "id2": {"jsonld": {"@id": "id2", "name": "Name 2"}}
    }
    
    node = {
        "items": [{"@id": "id1"}, {"@id": "id2"}, {"@id": "unknown"}]
    }
    
    changed = _resolve_node(node, lookup)
    assert changed is True
    assert node["items"][0]["name"] == "Name 1"
    assert node["items"][1]["name"] == "Name 2"
    assert node["items"][2] == {"@id": "unknown"}

def test_resolve_links_integration():
    client = MagicMock()
    
    # Mock search response
    doc1 = {
        "_id": "doc1",
        "_source": {
            "source": "src1",
            "s3_key": "k1",
            "graph": "g1",
            "jsonld": {
                "@id": "doc1",
                "link": {"@id": "doc2"}
            }
        }
    }
    doc2 = {
        "_id": "doc2",
        "_source": {
            "source": "src1",
            "s3_key": "k2",
            "graph": "g1",
            "jsonld": {
                "@id": "doc2",
                "name": "Resolved Name"
            }
        }
    }
    
    client.search.return_value = {
        "_scroll_id": "scroll123",
        "hits": {"hits": [doc1, doc2]}
    }
    client.scroll.return_value = {"hits": {"hits": []}} # End scroll
    
    # We need to mock helpers.bulk
    with MagicMock() as mock_bulk:
        import elasticsearch.helpers
        original_bulk = elasticsearch.helpers.bulk
        elasticsearch.helpers.bulk = mock_bulk
        mock_bulk.return_value = (1, [])
        
        resolve_links(client, "test-index", "src1")
        
        # Check if bulk was called with the updated document
        assert mock_bulk.called
        args, kwargs = mock_bulk.call_args
        actions = list(args[1])
        assert len(actions) == 1
        assert actions[0]["_id"] == "doc1"
        assert actions[0]["doc"]["jsonld"]["link"]["name"] == "Resolved Name"
        
        elasticsearch.helpers.bulk = original_bulk

if __name__ == "__main__":
    # Manual run
    logging.basicConfig(level=logging.INFO)
    test_resolve_node_basic()
    test_resolve_node_list()
    print("All tests passed!")
