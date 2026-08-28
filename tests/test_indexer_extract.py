from __future__ import annotations

import json

from indexer.extract import documents_from_jsonld_bytes, extract_document


def test_extract_simple() -> None:
    node = {
        "@context": "https://schema.org/",
        "@type": "Dataset",
        "@id": "https://example.org/d1",
        "name": "Example Dataset",
        "description": "A test description",
        "keywords": ["ocean", "temp"],
        "url": "https://example.org/d1.html",
    }
    doc = extract_document(
        node,
        source="medin",
        s3_key="summoned/medin/abc.json",
        graph="urn:odis:medin",
        source_url="https://example.org/page-harvested",
    )
    assert doc["name"] == "Example Dataset"
    assert doc["description"] == "A test description"
    assert doc["keywords"] == ["ocean", "temp"]
    assert doc["type"] == ["Dataset"]
    assert doc["id"] == "https://example.org/d1"
    assert doc["_id"] == "https://example.org/d1"
    assert doc["url"] == "https://example.org/d1.html"
    assert doc["source_url"] == "https://example.org/page-harvested"
    assert doc["jsonld"]["@type"] == "Dataset"


def test_extract_defined_term_keywords() -> None:
    node = {
        "@type": "Dataset",
        "name": "X",
        "keywords": [
            {"@type": "DefinedTerm", "name": "current", "termCode": "N01"},
            "waves",
        ],
    }
    doc = extract_document(node, source="m", s3_key="k.json", graph="urn:odis:m")
    assert "current" in doc["keywords"]
    assert "waves" in doc["keywords"]


def test_array_root_multiple_docs(read_fixture) -> None:
    # page_multi style: list of two objects
    body = json.dumps(
        [
            {"@type": "Organization", "name": "Org", "@id": "https://example.org/org"},
            {"@type": "Dataset", "name": "Data", "@id": "https://example.org/data"},
        ]
    )
    docs = documents_from_jsonld_bytes(
        body, source="medin", s3_key="summoned/medin/x.json", graph="urn:odis:medin"
    )
    assert len(docs) == 2
    names = {d["name"] for d in docs}
    assert names == {"Org", "Data"}


def test_url_list_takes_first() -> None:
    node = {"@type": "DataCatalog", "name": "C", "url": ["https://a.example/", "https://b.example/"]}
    doc = extract_document(node, source="m", s3_key="k.json", graph="urn:odis:m")
    assert doc["url"] == "https://a.example/"


def test_direct_jsonld_fixture(read_fixture) -> None:
    docs = documents_from_jsonld_bytes(
        read_fixture("direct.jsonld"),
        source="x",
        s3_key="summoned/x/1.json",
        graph="urn:odis:x",
    )
    assert len(docs) == 1
    assert docs[0]["name"] == "Direct JSON-LD"


def test_extract_ioos_prefixed_fields() -> None:
    node = {
        "@context": {
            "@vocab": "https://schema.org/",
            "schema": "https://schema.org/",
        },
        "@type": "schema:Dataset",
        "@id": "https://ioos.noaa.gov/dataset/waves-1",
        "schema:name": "IOOS Wave Height Observation",
        "schema:description": "Real-time wave observations across coastal US",
        "schema:keywords": ["waves", "buoy", "height"],
        "schema:url": "https://ioos.noaa.gov/waves-1",
    }
    doc = extract_document(
        node,
        source="ioos",
        s3_key="summoned/ioos/123.json",
        graph="urn:odis:ioos",
        source_url="https://ioos.noaa.gov/harvest/page",
    )
    assert doc["name"] == "IOOS Wave Height Observation"
    assert doc["description"] == "Real-time wave observations across coastal US"
    assert doc["keywords"] == ["waves", "buoy", "height"]
    assert doc["url"] == "https://ioos.noaa.gov/waves-1"
    assert doc["type"] == ["Dataset"]
    assert doc["id"] == "https://ioos.noaa.gov/dataset/waves-1"


def test_extract_custom_context_mapping() -> None:
    node = {
        "@context": {
            "schema": "https://schema.org/",
            "title": "schema:name",
            "abstract": "schema:description",
            "link": "schema:url",
            "tags": "schema:keywords",
        },
        "@type": "schema:Dataset",
        "title": "Mapped Dataset",
        "abstract": "Mapped Description",
        "link": "https://example.org/dataset",
        "tags": ["ocean", "sensors"],
    }
    doc = extract_document(
        node,
        source="custom",
        s3_key="summoned/custom/1.json",
        graph="urn:odis:custom",
    )
    assert doc["name"] == "Mapped Dataset"
    assert doc["description"] == "Mapped Description"
    assert doc["url"] == "https://example.org/dataset"
    assert doc["keywords"] == ["ocean", "sensors"]


def test_extract_top_level_context_with_graph() -> None:
    body = json.dumps(
        {
            "@context": {
                "schema": "https://schema.org/",
            },
            "@graph": [
                {
                    "@id": "https://example.org/item1",
                    "@type": "schema:Dataset",
                    "schema:name": "Item 1",
                    "schema:description": "Description 1",
                    "schema:url": "https://example.org/item1",
                },
                {
                    "@id": "https://example.org/item2",
                    "@type": "schema:Dataset",
                    "schema:name": "Item 2",
                    "schema:description": "Description 2",
                    "schema:url": "https://example.org/item2",
                },
            ],
        }
    )
    docs = documents_from_jsonld_bytes(
        body,
        source="ioos",
        s3_key="summoned/ioos/graph.json",
        graph="urn:odis:ioos",
    )
    assert len(docs) == 2
    assert docs[0]["name"] == "Item 1"
    assert docs[0]["description"] == "Description 1"
    assert docs[0]["url"] == "https://example.org/item1"
    assert docs[0]["type"] == ["Dataset"]
    assert docs[1]["name"] == "Item 2"


def test_extract_nested_prefixed_defined_term() -> None:
    node = {
        "@context": {
            "schema": "https://schema.org/",
        },
        "@type": "schema:Dataset",
        "schema:name": "Dataset with DefinedTerm",
        "schema:keywords": [
            {
                "@type": "schema:DefinedTerm",
                "schema:name": "Salinity",
                "schema:termCode": "SAL01",
            }
        ],
    }
    doc = extract_document(
        node,
        source="test",
        s3_key="summoned/test/1.json",
        graph="urn:odis:test",
    )
    assert doc["name"] == "Dataset with DefinedTerm"
    assert "Salinity" in doc["keywords"]
