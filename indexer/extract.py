"""Extract searchable facade documents from JSON-LD."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class JsonLdContext:
    """Helper to resolve JSON-LD context terms and prefixes."""

    def __init__(self, context_data: Any = None, parent: JsonLdContext | None = None):
        if parent is not None:
            self.vocab = parent.vocab
            self.prefixes = dict(parent.prefixes)
            self.terms = dict(parent.terms)
        else:
            self.vocab = None
            self.prefixes = {
                "schema": "https://schema.org/",
                "sdo": "https://schema.org/",
                "dct": "http://purl.org/dc/terms/",
                "dcterms": "http://purl.org/dc/terms/",
                "dc": "http://purl.org/dc/elements/1.1/",
                "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                "dcat": "http://www.w3.org/ns/dcat#",
                "skos": "http://www.w3.org/2004/02/skos/core#",
                "foaf": "http://xmlns.com/foaf/0.1/",
                "prov": "http://www.w3.org/ns/prov#",
            }
            self.terms = {}
        if context_data:
            self.parse(context_data)

    def parse(self, context_data: Any) -> None:
        if isinstance(context_data, str):
            ctx_str = context_data.strip()
            if "schema.org" in ctx_str:
                self.vocab = "https://schema.org/"
                self.prefixes["schema"] = "https://schema.org/"
            elif ctx_str.startswith(("http://", "https://")):
                self.vocab = ctx_str if ctx_str.endswith(("/", "#")) else ctx_str + "/"
        elif isinstance(context_data, list):
            for item in context_data:
                self.parse(item)
        elif isinstance(context_data, dict):
            for k, v in context_data.items():
                if k == "@vocab" and isinstance(v, str):
                    if "schema.org" in v:
                        self.vocab = "https://schema.org/"
                    else:
                        self.vocab = v if v.endswith(("/", "#")) else v + "/"
                elif isinstance(v, str):
                    if v.endswith(("/", "#", ":")) and not v.startswith(
                        ("http://schema.org", "https://schema.org")
                    ):
                        self.prefixes[k] = v
                    elif "schema.org" in v and (v.endswith("/") or v.endswith("#")):
                        self.prefixes[k] = "https://schema.org/"
                    else:
                        self.terms[k] = self._resolve_target(v)
                elif isinstance(v, dict):
                    target_id = v.get("@id")
                    if isinstance(target_id, str):
                        self.terms[k] = self._resolve_target(target_id)

    def _resolve_target(self, target: str) -> str:
        if target.startswith("http://schema.org/"):
            return "https://schema.org/" + target[len("http://schema.org/"):]
        if target.startswith(("http://", "https://", "urn:")):
            return target
        if ":" in target:
            prefix, suffix = target.split(":", 1)
            if prefix in self.prefixes:
                return f"{self.prefixes[prefix]}{suffix}"
        elif self.vocab:
            return f"{self.vocab}{target}"
        return target

    def expand_key(self, key: str) -> str:
        if key.startswith("@"):
            return key
        if key in self.terms:
            return self._resolve_target(self.terms[key])
        if key.startswith("http://schema.org/"):
            return "https://schema.org/" + key[len("http://schema.org/"):]
        if key.startswith(("http://", "https://", "urn:")):
            return key
        if ":" in key:
            prefix, suffix = key.split(":", 1)
            if prefix in self.prefixes:
                return f"{self.prefixes[prefix]}{suffix}"
            return key
        if self.vocab:
            return f"{self.vocab}{key}"
        return key


def _get_field(
    node: dict[str, Any],
    candidate_iris: list[str],
    context: JsonLdContext | None = None,
) -> Any:
    ctx = context or JsonLdContext()
    expanded_map: dict[str, Any] = {}
    for k, v in node.items():
        expanded_k = ctx.expand_key(k)
        expanded_map[expanded_k] = v
        expanded_map[k] = v
        if expanded_k.startswith("https://schema.org/"):
            short_k = expanded_k[len("https://schema.org/"):]
            if short_k not in expanded_map:
                expanded_map[short_k] = v

    for candidate in candidate_iris:
        candidate_expanded = ctx.expand_key(candidate)
        if candidate_expanded in expanded_map:
            val = expanded_map[candidate_expanded]
            if val is not None:
                return val
        if candidate in expanded_map:
            val = expanded_map[candidate]
            if val is not None:
                return val
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _plain_string(value: Any, context: JsonLdContext | None = None) -> str | None:
    """Coerce Schema.org-ish values to a plain string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        ctx = context or JsonLdContext(value.get("@context"))
        if "@value" in value:
            return _plain_string(value.get("@value"), ctx)
        val = _get_field(
            value,
            [
                "https://schema.org/name",
                "https://schema.org/text",
                "https://schema.org/value",
                "https://schema.org/termCode",
                "@value",
                "name",
                "text",
                "value",
                "termCode",
            ],
            ctx,
        )
        if val is not None:
            return _plain_string(val, ctx)
        # simple language map: pick first string value
        for v in value.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None
    if isinstance(value, list):
        for item in value:
            s = _plain_string(item, context)
            if s:
                return s
        return None
    return str(value)


def _string_list(value: Any, context: JsonLdContext | None = None) -> list[str]:
    out: list[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            ctx = context or JsonLdContext(item.get("@context"))
            # DefinedTerm etc.: prefer name, then termCode, then @id
            val = _get_field(
                item,
                [
                    "https://schema.org/name",
                    "https://schema.org/termCode",
                    "@id",
                    "https://schema.org/identifier",
                    "https://schema.org/value",
                    "name",
                    "termCode",
                    "identifier",
                    "value",
                ],
                ctx,
            )
            s = _plain_string(val, ctx) or _plain_string(item, ctx)
        else:
            s = _plain_string(item, context)
        if s and s not in out:
            out.append(s)
    return out


def _type_list(value: Any, context: JsonLdContext | None = None) -> list[str]:
    types: list[str] = []
    for item in _as_list(value):
        if isinstance(item, str):
            item_str = item.strip()
            if item_str.startswith(("http://", "https://", "urn:")):
                t = item_str.rsplit("/", 1)[-1].rsplit("#", 1)[-1].rsplit(":", 1)[-1]
            elif ":" in item_str:
                t = item_str.split(":", 1)[-1]
            else:
                t = item_str
            if t and t not in types:
                types.append(t)
        elif isinstance(item, dict):
            ctx = context or JsonLdContext(item.get("@context"))
            val = _get_field(item, ["@id", "https://schema.org/name", "name"], ctx)
            s = _plain_string(val, ctx) if val else None
            if s:
                if s.startswith(("http://", "https://", "urn:")):
                    t = s.rsplit("/", 1)[-1].rsplit("#", 1)[-1].rsplit(":", 1)[-1]
                elif ":" in s:
                    t = s.split(":", 1)[-1]
                else:
                    t = s
                if t and t not in types:
                    types.append(t)
        else:
            s = _plain_string(item, context)
            if s and s not in types:
                types.append(s)
    return types


def _doc_id(
    node: dict[str, Any],
    s3_key: str,
    index_in_file: int,
    context: JsonLdContext | None = None,
) -> str:
    ctx = context or JsonLdContext(node.get("@context"))
    rid = _get_field(node, ["@id", "id"], ctx)
    if isinstance(rid, str) and rid.strip():
        rid = rid.strip()
        # ES _id length limit; hash long IRIs
        if len(rid) <= 512:
            return rid
        return hashlib.sha1(rid.encode("utf-8")).hexdigest()
    base = s3_key.rsplit("/", 1)[-1]
    if index_in_file == 0:
        return base
    return f"{base}#{index_in_file}"


def extract_document(
    node: dict[str, Any],
    *,
    source: str,
    s3_key: str,
    graph: str,
    index_in_file: int = 0,
    source_url: str | None = None,
    context: JsonLdContext | None = None,
) -> dict[str, Any]:
    """Build one ES document with search facade + full jsonld.

    ``url`` is Schema.org resource/landing page from the JSON-LD.
    ``source_url`` is the harvest page URL recorded by summoner on S3 metadata.
    """
    ctx = JsonLdContext(node.get("@context"), parent=context)

    raw_name = _get_field(
        node,
        [
            "https://schema.org/name",
            "https://schema.org/headline",
            "http://purl.org/dc/terms/title",
            "http://purl.org/dc/elements/1.1/title",
            "http://www.w3.org/2000/01/rdf-schema#label",
            "name",
            "title",
            "headline",
            "label",
        ],
        ctx,
    )
    name = _plain_string(raw_name, ctx)

    raw_desc = _get_field(
        node,
        [
            "https://schema.org/description",
            "https://schema.org/abstract",
            "https://schema.org/disambiguatingDescription",
            "http://purl.org/dc/terms/description",
            "http://purl.org/dc/elements/1.1/description",
            "http://purl.org/dc/terms/abstract",
            "description",
            "abstract",
            "summary",
            "disambiguatingDescription",
        ],
        ctx,
    )
    description = _plain_string(raw_desc, ctx)

    raw_keywords = _get_field(
        node,
        [
            "https://schema.org/keywords",
            "https://schema.org/keyword",
            "http://purl.org/dc/terms/subject",
            "http://purl.org/dc/elements/1.1/subject",
            "keywords",
            "keyword",
            "subject",
            "tags",
            "tag",
        ],
        ctx,
    )
    keywords = _string_list(raw_keywords, ctx)

    raw_urls = _get_field(
        node,
        [
            "https://schema.org/url",
            "http://www.w3.org/ns/dcat#landingPage",
            "https://schema.org/landingPage",
            "https://schema.org/mainEntityOfPage",
            "https://schema.org/distribution",
            "https://schema.org/contentUrl",
            "url",
            "link",
            "landingPage",
            "mainEntityOfPage",
        ],
        ctx,
    )
    urls = _string_list(raw_urls, ctx)
    url = urls[0] if urls else None

    raw_id = _get_field(node, ["@id", "id"], ctx)
    doc_id_val = _plain_string(raw_id, ctx)

    raw_type = _get_field(
        node,
        ["@type", "type", "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"],
        ctx,
    )
    types = _type_list(raw_type, ctx)

    doc: dict[str, Any] = {
        "source": source,
        "s3_key": s3_key,
        "graph": graph,
        "id": doc_id_val,
        "type": types,
        "name": name,
        "description": description,
        "keywords": keywords,
        "url": url,
        "source_url": source_url,
        "jsonld": node,
        "_id": _doc_id(node, s3_key, index_in_file, ctx),
    }
    return doc


def documents_from_jsonld_bytes(
    body: bytes | str,
    *,
    source: str,
    s3_key: str,
    graph: str,
    source_url: str | None = None,
) -> list[dict[str, Any]]:
    """Parse JSON-LD object or array into one or more ES documents."""
    if isinstance(body, bytes):
        text = body.decode("utf-8")
    else:
        text = body

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON in %s: %s", s3_key, exc)
        return []

    top_context: JsonLdContext | None = None
    nodes: list[Any]
    if isinstance(data, list):
        nodes = data
    elif isinstance(data, dict):
        if "@context" in data:
            top_context = JsonLdContext(data["@context"])
        # Expand @graph if present at top level alongside other keys rarely
        if "@graph" in data and isinstance(data["@graph"], list):
            nodes = data["@graph"]
        else:
            nodes = [data]
    else:
        logger.warning("Unexpected JSON root type in %s: %s", s3_key, type(data))
        return []

    docs: list[dict[str, Any]] = []
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        docs.append(
            extract_document(
                node,
                source=source,
                s3_key=s3_key,
                graph=graph,
                index_in_file=i,
                source_url=source_url,
                context=top_context,
            )
        )
    return docs

