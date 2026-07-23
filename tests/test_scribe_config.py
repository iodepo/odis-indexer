from __future__ import annotations

from pathlib import Path

import pytest

from scribe.config import (
    activity_iri,
    agent_iri,
    graph_iri,
    load_config,
    object_iri,
    prov_graph_iri,
)


def test_load_config(fixtures_dir: Path) -> None:
    cfg = load_config(fixtures_dir / "scribe_config.yaml")
    assert cfg.objectstore.bucket == "iode"
    assert cfg.objectstore.ssl is False
    assert cfg.triplestore.type == "oxigraph"
    assert cfg.triplestore.base_endpoint == "http://localhost:7878"


def test_graph_iri() -> None:
    assert graph_iri("medin") == "urn:odis:medin"
    assert graph_iri("bodc") == "urn:odis:bodc"
    assert graph_iri("  cioos ") == "urn:odis:cioos"


def test_prov_graph_iri() -> None:
    assert prov_graph_iri("medin") == "urn:odis:prov:medin"
    assert prov_graph_iri("  bodc ") == "urn:odis:prov:bodc"


def test_object_and_activity_iri() -> None:
    assert object_iri("medin", "abc") == "urn:odis:object:medin:abc"
    assert activity_iri("medin", "abc") == "urn:odis:activity:scribe:medin:abc"
    assert agent_iri() == "urn:odis:agent:scribe"


def test_graph_iri_empty() -> None:
    with pytest.raises(ValueError):
        graph_iri("   ")
    with pytest.raises(ValueError):
        prov_graph_iri("   ")


def test_missing_triplestore(tmp_path: Path) -> None:
    p = tmp_path / "cfg.yaml"
    p.write_text(
        """
objectstore:
  address: localhost
  port: 4566
  accessKey: a
  secretKey: b
  ssl: false
  bucket: b1
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="triplestore"):
        load_config(p)


def test_unsupported_store_type(tmp_path: Path) -> None:
    p = tmp_path / "cfg.yaml"
    p.write_text(
        """
objectstore:
  address: localhost
  port: 4566
  accessKey: a
  secretKey: b
  ssl: false
  bucket: b1
triplestore:
  type: graphdb
  endpoint: http://localhost:7200
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="oxigraph"):
        load_config(p)
