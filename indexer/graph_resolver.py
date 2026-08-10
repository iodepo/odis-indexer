import logging
from typing import Any, Dict, List, Optional
from elasticsearch import Elasticsearch, helpers

logger = logging.getLogger(__name__)

def resolve_links(client: Elasticsearch, index: str, source: str):
    """
    Second pass to resolve @id links within the same index/source.
    It looks for fields that only have an @id and tries to find the full document
    in the same index to embed its data.
    """
    logger.info("Starting graph resolution for source '%s' in index '%s'", source, index)
    
    # 1. Fetch all documents for this source
    # We use scroll or search since we might have many documents
    query = {
        "query": {
            "term": {"source": source}
        }
    }
    
    # Initialize scroll
    resp = client.search(
        index=index,
        body=query,
        scroll='2m',
        size=100
    )

    scroll_id = resp.get('_scroll_id')
    hits = resp.get('hits', {}).get('hits', [])
    
    # We'll collect all documents first to build a lookup map
    # In a very large index, we might want to do this differently, 
    # but for ODIS it's usually manageable in memory.
    lookup: Dict[str, Dict[str, Any]] = {}
    docs_to_process = []

    while hits:
        for hit in hits:
            doc = hit['_source']
            doc_id = hit['_id']
            lookup[doc_id] = doc
            # Also lookup by the 'id' field in jsonld if it differs from ES _id
            jsonld_id = doc.get('jsonld', {}).get('@id')
            if jsonld_id:
                lookup[jsonld_id] = doc
            docs_to_process.append(hit)

        resp = client.scroll(scroll_id=scroll_id, scroll='2m')
        scroll_id = resp.get('_scroll_id')
        hits = resp.get('hits', {}).get('hits', [])

    client.clear_scroll(scroll_id=scroll_id)

    updated_count = 0
    actions = []

    for hit in docs_to_process:
        doc = hit['_source']
        original_jsonld = doc.get('jsonld', {})
        
        # Deep walk to find @id links
        changed = _resolve_node(original_jsonld, lookup)
        
        if changed:
            # Re-extract searchable fields if needed? 
            # For now, we primarily want to update the jsonld itself.
            # But the facade might need updates too (e.g. if name was missing and now resolved)
            # However, extract_document is usually called during load.
            # We'll just update the ES document with the enriched jsonld.
            
            # TODO: Should we re-run extraction? 
            # If the resolution added a name or description that was missing, yes.
            from .extract import extract_document
            new_doc = extract_document(
                original_jsonld,
                source=doc['source'],
                s3_key=doc['s3_key'],
                graph=doc['graph'],
                source_url=doc.get('source_url')
            )
            
            actions.append({
                "_op_type": "update",
                "_index": index,
                "_id": hit['_id'],
                "doc": new_doc
            })
            updated_count += 1

    if actions:
        success, errors = helpers.bulk(client, actions, raise_on_error=False)
        logger.info("Graph resolution complete: %d documents updated, %d successes, %d errors", 
                    updated_count, success, len(errors) if isinstance(errors, list) else errors)
    else:
        logger.info("Graph resolution complete: no documents needed updates")

def _resolve_node(node: Any, lookup: Dict[str, Dict[str, Any]], depth: int = 0) -> bool:
    """Recursively resolve @id links in a JSON-LD node. Returns True if any change was made."""
    if depth > 5: # Prevent infinite recursion
        return False
    
    changed = False
    if isinstance(node, dict):
        # Check if this node is just an @id link
        if len(node) == 1 and "@id" in node:
            ref_id = node["@id"]
            if ref_id in lookup:
                ref_doc = lookup[ref_id]
                ref_jsonld = ref_doc.get("jsonld", {})
                # Merge info. We don't want to overwrite everything, 
                # but we want to provide the substance.
                for k, v in ref_jsonld.items():
                    if k not in node:
                        node[k] = v
                        changed = True
                return changed

        # Otherwise, recurse into all properties
        for k, v in list(node.items()):
            if _resolve_node(v, lookup, depth + 1):
                changed = True
    elif isinstance(node, list):
        for i, item in enumerate(node):
            if isinstance(item, dict):
                # Special case: if item is an @id link in a list
                if len(item) == 1 and "@id" in item:
                    ref_id = item["@id"]
                    if ref_id in lookup:
                        ref_doc = lookup[ref_id]
                        node[i] = ref_doc.get("jsonld", {}).copy()
                        changed = True
                else:
                    if _resolve_node(item, lookup, depth + 1):
                        changed = True
    return changed
