import logging
from indexer.errors import ErrorLimiter

def test_es_error_patterns():
    limiter = ErrorLimiter(limit=2)
    messages = []
    
    # Test cases based on the issue description
    errors = [
        "WARNING elastic_transport.node_pool: Node <Urllib3HttpNode(http://localhost:9200)> has failed for 1 times in a row, putting on 1 second timeout",
        "WARNING elastic_transport.transport: Retrying request after failure (attempt 0 of 3)",
        "http.client.RemoteDisconnected: Remote end closed connection without response",
        "urllib3.exceptions.ProtocolError: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))",
        "elastic_transport.ConnectionError: Connection error caused by: ProtocolError(('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')))",
        "ERROR indexer.load: Failed to update odiscat for marco-bolo-dataset-catalogue: Connection error caused by: ConnectionError(Connection error caused by: ProtocolError(('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))))"
    ]
    
    print("Testing error patterns...")
    for err in errors:
        added = limiter.add_error(err, messages)
        print(f"Added: {added} | Message: {err[:50]}...")

    print("\nResulting messages:")
    for m in messages:
        print(f"  - {m}")
    
    # Verify groupings
    # Node failure -> 1
    # Retry -> 1
    # RemoteDisconnected -> 1
    # ProtocolError -> 1
    # Connection error caused by ProtocolError (which contains RemoteDisconnected) -> matched by RemoteDisconnected pattern if first, or ProtocolError
    
    # Actually let's check which patterns they matched
    for err in errors:
        key = limiter._get_key(err)
        print(f"Error: {err[:30]}... -> Key: {key}")

if __name__ == "__main__":
    test_es_error_patterns()
