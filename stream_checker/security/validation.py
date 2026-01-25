"""Input validation and security checks"""

import re
import ipaddress
from urllib.parse import urlparse
from typing import List, Tuple, Optional


class ValidationError(Exception):
    """Raised when validation fails"""
    pass


class URLValidator:
    """Validates stream URLs"""
    
    def __init__(
        self,
        allowed_schemes: List[str] = None,
        block_private_ips: bool = False,
        max_url_length: int = 2048
    ):
        self.allowed_schemes = allowed_schemes or ["http", "https"]
        self.block_private_ips = block_private_ips
        self.max_url_length = max_url_length
        
        # Dangerous schemes to block
        self.blocked_schemes = [
            "file", "ftp", "javascript", "data", "mailto", "tel",
            "ssh", "sftp", "gopher", "ldap"
        ]
    
    def validate(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate URL
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not url or not isinstance(url, str):
            return False, "URL must be a non-empty string"
        
        # Check length
        if len(url) > self.max_url_length:
            return False, f"URL exceeds maximum length of {self.max_url_length} characters"
        
        # Parse URL
        try:
            parsed = urlparse(url)
        except Exception as e:
            return False, f"Invalid URL format: {str(e)}"
        
        # Check scheme
        if not parsed.scheme:
            return False, "URL must include a scheme (http:// or https://)"
        
        scheme = parsed.scheme.lower()
        
        # Block dangerous schemes
        if scheme in self.blocked_schemes:
            return False, f"Scheme '{scheme}' is not allowed"
        
        # Check if scheme is in allowed list
        if scheme not in self.allowed_schemes:
            return False, f"Scheme '{scheme}' is not allowed. Allowed schemes: {', '.join(self.allowed_schemes)}"
        
        # Check netloc (hostname)
        if not parsed.netloc:
            return False, "URL must include a hostname"
        
        # Check for private IP addresses
        if self.block_private_ips:
            hostname = parsed.hostname
            if hostname:
                try:
                    # Try to resolve as IP address
                    ip = ipaddress.ip_address(hostname)
                    if ip.is_private or ip.is_loopback or ip.is_link_local:
                        return False, f"Private/internal IP addresses are not allowed: {hostname}"
                except ValueError:
                    # Not an IP address, check if it's a private domain
                    if hostname in ["localhost", "127.0.0.1", "0.0.0.0"]:
                        return False, f"Localhost addresses are not allowed: {hostname}"
        
        # Basic path validation (prevent path traversal attempts)
        if parsed.path and ("../" in parsed.path or "..\\" in parsed.path):
            return False, "Path traversal attempts are not allowed"
        
        return True, None
    
    def validate_and_raise(self, url: str):
        """Validate URL and raise exception if invalid"""
        is_valid, error = self.validate(url)
        if not is_valid:
            raise ValidationError(error)
        return True


def validate_phase(phase: int) -> bool:
    """Validate phase number (1-4)"""
    if not isinstance(phase, int):
        return False
    return 1 <= phase <= 4


def validate_silence_threshold(threshold: float) -> bool:
    """Validate silence threshold in dB (-100 to 0)"""
    if not isinstance(threshold, (int, float)):
        return False
    return -100 <= threshold <= 0


def validate_sample_duration(duration: int) -> bool:
    """Validate sample duration in seconds (1 to 300)"""
    if not isinstance(duration, int):
        return False
    return 1 <= duration <= 300
