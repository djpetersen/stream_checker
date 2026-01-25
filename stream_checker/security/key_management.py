"""Key management for test runs and streams"""

import uuid
import hashlib
from urllib.parse import urlparse, parse_qs, urlencode


def generate_test_run_id() -> str:
    """Generate a unique test run ID (UUID v4)"""
    return str(uuid.uuid4())


def generate_stream_id(url: str) -> str:
    """
    Generate a deterministic stream ID from URL
    
    Args:
        url: Stream URL
        
    Returns:
        First 16 characters of SHA-256 hash of normalized URL
    """
    normalized = normalize_url(url)
    stream_hash = hashlib.sha256(normalized.encode()).hexdigest()
    return stream_hash[:16]


def normalize_url(url: str) -> str:
    """
    Normalize URL for consistent stream ID generation
    
    Args:
        url: Stream URL
        
    Returns:
        Normalized URL string
    """
    # Parse URL
    parsed = urlparse(url.lower().strip())
    
    # Reconstruct normalized URL
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    
    # Sort query parameters for consistency
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        # Sort by key, then by value
        sorted_params = sorted(params.items())
        query_string = urlencode(sorted_params, doseq=True)
        normalized += '?' + query_string
    
    # Note: We intentionally exclude fragment (#) as it's not sent to server
    
    return normalized
