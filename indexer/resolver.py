import logging
import httpx
from typing import Any, Dict, Optional
# from pyld import jsonld

logger = logging.getLogger(__name__)

class Resolver:
    def __init__(self, triplestore_endpoint: Optional[str] = None):
        self.triplestore_endpoint = triplestore_endpoint.rstrip("/") if triplestore_endpoint else None
        self.cache: Dict[str, Any] = {}
        self.client = httpx.Client(timeout=10.0)
        self.local_context: Dict[str, Any] = {}

    def set_local_context(self, context: Dict[str, Any]):
        """Set a dictionary of @id -> data to search before external resolution."""
        self.local_context = context

    def resolve(self, uri: str) -> Optional[Dict[str, Any]]:
        if not uri or not uri.startswith("http"):
            return None
        
        # 0. Try local context
        if uri in self.local_context:
            logger.info("Resolver: <%s> found in [LOCAL CONTEXT]", uri)
            return self.local_context[uri]
        
        if uri in self.cache:
            logger.debug("Resolver: <%s> found in [CACHE]", uri)
            return self.cache[uri]
        
        logger.info("Resolver: Looking up link <%s> [EXTERNAL]", uri)
        
        # 1. Try Oxigraph
        if self.triplestore_endpoint:
            resolved = self._resolve_from_oxigraph(uri)
            if resolved:
                logger.info("Resolver: Resolved <%s> from [TRIPLESTORE]", uri)
                self.cache[uri] = resolved
                return resolved

        # 2. Try Online resource
        resolved = self._resolve_from_web(uri)
        if resolved:
            logger.info("Resolver: Resolved <%s> from [WEB]", uri)
            self.cache[uri] = resolved
            return resolved

        logger.warning("Resolver: [NOT FOUND] Could not resolve <%s>", uri)
        return None

    def _resolve_from_oxigraph(self, uri: str) -> Optional[Dict[str, Any]]:
        query = f"DESCRIBE <{uri}>"
        url = f"{self.triplestore_endpoint}/query"
        try:
            response = self.client.post(
                url,
                data={"query": query},
                headers={"Accept": "application/ld+json"}
            )
            if response.status_code == 200:
                data = response.json()
                if not data:
                    return None

                # Fallback if PyLD fails on Python 3.9
                # If data is a list (result of DESCRIBE), find the record with matching @id
                nodes = []
                if isinstance(data, list):
                    nodes = data
                elif isinstance(data, dict):
                    if "@graph" in data:
                        nodes = data["@graph"]
                    else:
                        nodes = [data]
                
                for node in nodes:
                    if node.get("@id") == uri:
                        return node
        except Exception as e:
            logger.debug("Failed to resolve %s from oxigraph: %s", uri, e)
        return None

    def _resolve_from_web(self, uri: str) -> Optional[Dict[str, Any]]:
        try:
            response = self.client.get(uri, headers={"Accept": "application/ld+json, application/json"})
            if response.status_code == 200:
                data = response.json()
                # Ensure it's a dict and has some info
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.debug("Failed to resolve %s from web: %s", uri, e)
        return None

    def expand_identifiers(self, data: Any, seen: Optional[set] = None) -> Any:
        """Recursively traverse data and replace @id-only dicts with resolved content."""
        if seen is None:
            seen = set()

        if isinstance(data, list):
            return [self.expand_identifiers(item, seen) for item in data]
        
        if isinstance(data, dict):
            # Check if it's an @id-only reference
            if len(data) == 1 and "@id" in data:
                uri = data["@id"]
                if uri in seen:
                    return data
                
                resolved = self.resolve(uri)
                if resolved:
                    # Avoid infinite recursion
                    new_seen = seen | {uri}
                    return self.expand_identifiers(resolved, new_seen)
            
            return {k: self.expand_identifiers(v, seen) for k, v in data.items()}
        
        return data

    def close(self):
        self.client.close()
