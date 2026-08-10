import logging
from typing import Any, Dict, List, Optional
from elasticsearch import Elasticsearch, helpers

logger = logging.getLogger(__name__)

def resolve_links(
    client: Elasticsearch, 
    index: str, 
    source: str, 
    error_limiter: Optional[Any] = None,
    stats_messages: Optional[List[str]] = None
):
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
    try:
        resp = client.search(
            index=index,
            body=query,
            scroll='2m',
            size=100
        )
    except Exception as exc:
        msg = f"Graph resolution initial search failed: {exc}"
        logger.error(msg)
        if error_limiter is not None and stats_messages is not None:
            error_limiter.add_error(msg, stats_messages)
        return

    scroll_id = resp.get('_scroll_id')
    hits = resp.get('hits', {}).get('hits', [])
    
    # We'll collect all documents first to build a lookup map
    # In a very large index, we might want to do this differently, 
    # but for ODIS it's usually manageable in memory.
    lookup: Dict[str, Dict[str, Any]] = {}
    docs_to_process = []

    try:
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
    except Exception as exc:
        msg = f"Graph resolution scroll failed: {exc}"
        logger.error(msg)
        if error_limiter is not None and stats_messages is not None:
            error_limiter.add_error(msg, stats_messages)
        # We'll still try to process what we have so far
    finally:
        if scroll_id:
            try:
                client.clear_scroll(scroll_id=scroll_id)
            except Exception:
                pass

    updated_count = 0
    actions = []

    for hit in docs_to_process:
        doc = hit['_source']
        original_jsonld = doc.get('jsonld', {})
        
        # Deep walk to find @id links
        # We work on a deep copy to avoid mutating our lookup map 
        # which would cause unexpected side effects or cycles during the pass.
        import copy
        jsonld_copy = copy.deepcopy(original_jsonld)
        changed = _resolve_node(jsonld_copy, lookup)
        
        if changed:
            # Re-run extraction with the enriched jsonld.
            from .extract import extract_document
            new_doc = extract_document(
                jsonld_copy,
                source=doc['source'],
                s3_key=doc['s3_key'],
                graph=doc['graph'],
                source_url=doc.get('source_url')
            )
            # Remove _id from the document body as it's a metadata field
            new_doc.pop("_id", None)
            
            actions.append({
                "_op_type": "update",
                "_index": index,
                "_id": hit['_id'],
                "doc": new_doc
            })
            updated_count += 1

    if actions:
        try:
            # Chunk the bulk actions to avoid "Unable to serialize to JSON" or "Request size too large"
            # though the former was likely due to recursion in the doc itself.
            chunk_size = 50 
            for i in range(0, len(actions), chunk_size):
                chunk = actions[i : i + chunk_size]
                success, errors = helpers.bulk(client, chunk, raise_on_error=False)
                logger.info("Graph resolution chunk: %d successes, %d errors", 
                            success, len(errors) if isinstance(errors, list) else errors)
                
                if errors and isinstance(errors, list):
                    for err in errors:
                        op = next(iter(err.keys()))
                        info = err[op]
                        if error_limiter is not None and stats_messages is not None:
                            msg = f"Graph Resolve ID {info.get('_id')}: {info.get('error', {}).get('reason', 'unknown error')}"
                            error_limiter.add_error(msg, stats_messages)
                        else:
                            logger.error(f"Bulk error for {info.get('_id')}: {info.get('error')}")
        except Exception as exc:
            msg = f"Graph resolution bulk update failed: {exc}"
            logger.error(msg)
            if error_limiter is not None and stats_messages is not None:
                error_limiter.add_error(msg, stats_messages)
    else:
        logger.info("Graph resolution complete: no documents needed updates")

def _resolve_node(node: Any, lookup: Dict[str, Dict[str, Any]], depth: int = 0, visited_ids: Optional[set] = None) -> bool:
    """Recursively resolve @id links in a JSON-LD node. Returns True if any change was made."""
    if depth > 5: # Prevent infinite recursion
        return False
    
    if visited_ids is None:
        visited_ids = set()

    changed = False
    if isinstance(node, dict):
        # Check if this node contains an @id link and potentially other metadata
        if "@id" in node:
            ref_id = node["@id"]
            
            # Cycle detection: if we've already resolved this ID in this path, stop
            if ref_id in visited_ids:
                return False
            
            if ref_id in lookup:
                ref_doc = lookup[ref_id]
                ref_jsonld = ref_doc.get("jsonld", {})
                
                # Merge info. Only merge if we haven't already merged substantial info
                substantial_keys = [k for k in node.keys() if k not in ("@id", "@type", "@context")]
                if not substantial_keys:
                    visited_ids.add(ref_id)
                    for k, v in ref_jsonld.items():
                        if k not in node:
                            # Use a shallow copy for values to avoid simple shared mutation
                            node[k] = v.copy() if isinstance(v, (dict, list)) else v
                            changed = True
                    
                    # After merging, try to resolve newly added properties
                    if _resolve_node(node, lookup, depth + 1, visited_ids):
                        changed = True
                    
                    visited_ids.remove(ref_id)
                    return changed

        # Otherwise, recurse into all properties
        for k, v in list(node.items()):
            if k == "@context": # Skip context resolution to avoid bloat/recursion
                continue
            if _resolve_node(v, lookup, depth + 1, visited_ids):
                changed = True
    elif isinstance(node, list):
        for i, item in enumerate(node):
            if isinstance(item, dict):
                if "@id" in item:
                    ref_id = item["@id"]
                    if ref_id in visited_ids:
                        continue
                        
                    if ref_id in lookup:
                        ref_doc = lookup[ref_id]
                        ref_jsonld = ref_doc.get("jsonld", {})
                        
                        substantial_keys = [k for k in item.keys() if k not in ("@id", "@type", "@context")]
                        if not substantial_keys:
                            visited_ids.add(ref_id)
                            # Replace with a copy
                            node[i] = ref_jsonld.copy()
                            changed = True
                            
                            # Recurse into the newly placed object
                            _resolve_node(node[i], lookup, depth + 1, visited_ids)
                            visited_ids.remove(ref_id)
                            continue

                if _resolve_node(item, lookup, depth + 1, visited_ids):
                    changed = True
    return changed
