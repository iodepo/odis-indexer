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


def _docs(data) -> list[dict]:
    return documents_from_jsonld_bytes(
        json.dumps(data), source="s", s3_key="summoned/s/a.json", graph="urn:odis:s"
    )


def test_flattened_graph_indexes_like_nested() -> None:
    # Flattened @graph as emitted by rdflib/CKAN (e.g. data.ioos.us): the
    # Dataset's Place and GeoShape are sibling blank nodes linked by @id.
    # The reference to another file (creator) is left for graph_resolver.
    creator = {"@id": "https://w3id.org/marco-bolo/mbo_person"}
    flattened = {
        "@context": {"schema": "http://schema.org/"},
        "@graph": [
            {
                "@id": "https://example.org/dataset/1",
                "@type": "schema:Dataset",
                "schema:name": "Cruise 1",
                "schema:creator": creator,
                "schema:spatialCoverage": {"@id": "_:Nplace"},
            },
            {"@id": "_:Nplace", "@type": "schema:Place", "schema:geo": {"@id": "_:Nshape"}},
            {"@id": "_:Nshape", "@type": "schema:GeoShape", "schema:box": "26.38 -91.16 26.39 -90.795"},
        ],
    }
    nested = {
        "@context": {"schema": "http://schema.org/"},
        "@id": "https://example.org/dataset/1",
        "@type": "schema:Dataset",
        "schema:name": "Cruise 1",
        "schema:creator": creator,
        "schema:spatialCoverage": {
            "@type": "schema:Place",
            "schema:geo": {"@type": "schema:GeoShape", "schema:box": "26.38 -91.16 26.39 -90.795"},
        },
    }
    flat_docs, nested_docs = _docs(flattened), _docs(nested)
    assert len(flat_docs) == len(nested_docs) == 1
    for field in ("_id", "id", "type", "name", "description", "keywords", "url"):
        assert flat_docs[0][field] == nested_docs[0][field]
    jsonld = flat_docs[0]["jsonld"]
    assert jsonld["schema:spatialCoverage"]["schema:geo"]["schema:box"] == "26.38 -91.16 26.39 -90.795"
    assert jsonld["schema:creator"] == creator


def test_yoast_graph_indexes_as_one_webpage() -> None:
    # Yoast SEO (WordPress) links a page's parts with "#" IRIs, not blank nodes.
    page = "https://example.org/news/item/"
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "@id": page,
                "name": "News item",
                "isPartOf": {"@id": "https://example.org/#website"},
                "breadcrumb": {"@id": page + "#breadcrumb"},
                "primaryImageOfPage": {"@id": page + "#primaryimage"},
            },
            {"@type": "ImageObject", "@id": page + "#primaryimage", "url": "https://example.org/a.jpg"},
            {"@type": "BreadcrumbList", "@id": page + "#breadcrumb", "itemListElement": []},
            {
                "@type": "WebSite",
                "@id": "https://example.org/#website",
                "name": "Example",
                "publisher": {"@id": "https://example.org/#organization"},
            },
            {"@type": "Organization", "@id": "https://example.org/#organization", "name": "Example Org"},
        ],
    }
    docs = _docs(data)
    assert [d["_id"] for d in docs] == [page]
    jsonld = docs[0]["jsonld"]
    assert jsonld["breadcrumb"]["@type"] == "BreadcrumbList"
    assert jsonld["primaryImageOfPage"]["url"] == "https://example.org/a.jpg"
    assert jsonld["isPartOf"]["publisher"]["name"] == "Example Org"


def test_self_reference_keeps_node_and_stays_a_reference() -> None:
    # e.g. MARCO-BOLO Person files: no name, and a nested reference back to
    # the Person. That doesn't make it a sub-node, and it isn't embedded in itself.
    person = "https://w3id.org/marco-bolo/mbo_person"
    data = {
        "@id": person,
        "@type": "Person",
        "givenName": "Ada",
        "subjectOf": {"@type": "Dataset", "about": {"@id": person}},
    }
    docs = _docs(data)
    assert [d["_id"] for d in docs] == [person]
    assert docs[0]["jsonld"]["subjectOf"]["about"] == {"@id": person}
