import json
import pytest
import respx
from httpx import Response
from indexer.resolver import Resolver
from indexer.extract import documents_from_jsonld_bytes

@respx.mock
def test_resolver_expansion():
    # Mock data to be resolved
    author_uri = "https://w3id.org/marco-bolo/mbo_d4907c57-3eee-4d41-b3b0-a0c0b9631802"
    author_data = {
        "@context": "https://schema.org/",
        "@id": author_uri,
        "@type": "Person",
        "name": "John Doe"
    }
    
    respx.get(author_uri).mock(return_value=Response(200, json=author_data))
    
    # Original document with ID reference
    doc_json = {
        "@context": {"@import": "https://schema.org/"},
        "@id": "https://example.org/dataset1",
        "@type": "Dataset",
        "name": "Test Dataset",
        "author": {"@id": author_uri}
    }
    
    resolver = Resolver(triplestore_endpoint=None)
    
    # Test the resolver directly
    resolved = resolver.resolve(author_uri)
    assert resolved == author_data
    
    # Test extraction with expansion
    docs = documents_from_jsonld_bytes(
        json.dumps(doc_json),
        source="test",
        s3_key="test/key.json",
        graph="urn:test",
        resolver=resolver
    )
    
    assert len(docs) == 1
    extracted_doc = docs[0]
    assert extracted_doc["jsonld"]["author"]["name"] == "John Doe"
    assert extracted_doc["jsonld"]["author"]["@id"] == author_uri
    
    resolver.close()

@respx.mock
def test_resolver_recursion_limit():
    # Test that it doesn't infinite loop if there's a circular ref
    uri1 = "https://example.org/1"
    uri2 = "https://example.org/2"
    
    respx.get(uri1).mock(return_value=Response(200, json={"@id": uri1, "next": {"@id": uri2}}))
    respx.get(uri2).mock(return_value=Response(200, json={"@id": uri2, "next": {"@id": uri1}}))
    
    resolver = Resolver(triplestore_endpoint=None)
    
    doc = {"@id": uri1}
    expanded = resolver.expand_identifiers(doc)
    
    # It should have expanded uri1, and inside uri1 it should have expanded uri2, 
    # and inside uri2 it should have stopped or just kept the @id for uri1
    assert expanded["@id"] == uri1
    assert expanded["next"]["@id"] == uri2
    # In my current implementation, it DOES expand uri2, and inside uri2 it finds {"@id": uri1}.
    # Since it's a new call to resolve(uri1), it might expand it again if not in cache.
    # But it IS in cache now.
    
    assert "name" not in expanded # Just checking it didn't crash
    resolver.close()

def test_resolver_local_context():
    # Test that resolver finds info in the same @graph/file
    author_uri = "https://w3id.org/marco-bolo/author1"
    doc_json = {
        "@context": "https://schema.org/",
        "@graph": [
            {
                "@id": "https://example.org/dataset1",
                "@type": "Dataset",
                "name": "Test Dataset",
                "author": {"@id": author_uri}
            },
            {
                "@id": author_uri,
                "@type": "Person",
                "name": "Local Author"
            }
        ]
    }
    
    resolver = Resolver(triplestore_endpoint=None)
    
    # Extraction should build local context and find "Local Author"
    docs = documents_from_jsonld_bytes(
        json.dumps(doc_json),
        source="test",
        s3_key="test/key.json",
        graph="urn:test",
        resolver=resolver
    )
    
    # There should be two documents (Dataset and Person) if both are top-level in @graph
    assert len(docs) == 2
    dataset_doc = next(d for d in docs if d["type"] == ["Dataset"])
    assert dataset_doc["jsonld"]["author"]["name"] == "Local Author"
    
    resolver.close()
