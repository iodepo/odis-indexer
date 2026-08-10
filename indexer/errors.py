import re
from typing import List, Dict

class ErrorLimiter:
    """Helper to limit repetitive error messages."""
    
    def __init__(self, limit: int = 10):
        self.limit = limit
        self.counts: Dict[str, int] = {}
        self.patterns = [
            (re.compile(r"Client error '404 Not Found' for url.*", re.I), "Client error '404 Not Found'"),
            (re.compile(r"timeout|timed out|putting on \d+ second timeout", re.I), "Connection timeout"),
            (re.compile(r"Invalid XML sitemap: not well-formed \(invalid token\):.*", re.I), "Invalid XML sitemap: not well-formed"),
            (re.compile(r"no application/ld\+json script tags found.*", re.I), "No JSON-LD script tags found"),
            (re.compile(r"JSON body does not look like JSON-LD.*", re.I), "JSON body does not look like JSON-LD"),
            (re.compile(r"Could not parse sitemap.*", re.I), "Could not parse sitemap"),
            (re.compile(r"Failed to fetch sitemap.*", re.I), "Failed to fetch sitemap"),
            (re.compile(r"Sitemap recursion depth exceeded.*", re.I), "Sitemap recursion depth exceeded"),
            (re.compile(r"Connection aborted|Connection error caused by:.*Connection aborted", re.I), "Elasticsearch connection aborted"),
            (re.compile(r"RemoteDisconnected|Connection error caused by:.*RemoteDisconnected", re.I), "Elasticsearch remote disconnected"),
            (re.compile(r"ProtocolError|Connection error caused by:.*ProtocolError", re.I), "Elasticsearch protocol error"),
            (re.compile(r"Node <.*> has failed for .* times in a row", re.I), "Elasticsearch node failure"),
            (re.compile(r"Retrying request after failure \(attempt \d of \d\)", re.I), "Elasticsearch retry"),
        ]

    def _get_key(self, message: str) -> str:
        for pattern, key in self.patterns:
            if pattern.search(message):
                return key
        return message

    def add_error(self, message: str, message_list: List[str]) -> bool:
        """
        Adds an error message to the list if the limit for its type hasn't been reached.
        Returns True if the message was added, False otherwise.
        """
        key = self._get_key(message)
        count = self.counts.get(key, 0)
        
        if count < self.limit:
            message_list.append(message)
            self.counts[key] = count + 1
            return True
        elif count == self.limit:
            message_list.append(f"... similar errors occurred multiple times: {key}")
            self.counts[key] = count + 1
            return False
        else:
            self.counts[key] = count + 1
            return False
