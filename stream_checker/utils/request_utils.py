"""Utility functions for request handling and IP extraction"""

from typing import Optional


def get_client_ip(request) -> Optional[str]:
    """
    Extract client IP address from request object
    
    Handles:
    - Direct client IP
    - Proxy headers (X-Forwarded-For, X-Real-IP)
    - Load balancer headers (AWS ALB, CloudFront)
    
    Args:
        request: Flask request or FastAPI Request object
        
    Returns:
        IP address string or None
    """
    # Try Flask request
    if hasattr(request, 'remote_addr'):
        ip = request.remote_addr
        if ip:
            return ip
    
    # Try FastAPI request
    if hasattr(request, 'client'):
        if request.client and request.client.host:
            return request.client.host
    
    # Check proxy headers (in order of preference)
    headers_to_check = [
        'X-Forwarded-For',
        'X-Real-IP',
        'CF-Connecting-IP',  # Cloudflare
        'True-Client-IP',    # Cloudflare Enterprise
        'X-Client-IP',
        'X-Forwarded',
        'Forwarded-For',
        'Forwarded'
    ]
    
    for header in headers_to_check:
        value = None
        if hasattr(request, 'headers'):
            # FastAPI or Flask
            if hasattr(request.headers, 'get'):
                value = request.headers.get(header)
            elif isinstance(request.headers, dict):
                value = request.headers.get(header)
        
        if value:
            # X-Forwarded-For can contain multiple IPs (client, proxy1, proxy2)
            # Take the first one (original client)
            ip = value.split(',')[0].strip()
            if ip:
                return ip
    
    return None


def get_user_agent(request) -> Optional[str]:
    """
    Extract User-Agent from request
    
    Args:
        request: Flask request or FastAPI Request object
        
    Returns:
        User-Agent string or None
    """
    if hasattr(request, 'headers'):
        if hasattr(request.headers, 'get'):
            return request.headers.get('User-Agent')
        elif isinstance(request.headers, dict):
            return request.headers.get('User-Agent')
    return None


def get_referer(request) -> Optional[str]:
    """
    Extract Referer from request
    
    Args:
        request: Flask request or FastAPI Request object
        
    Returns:
        Referer string or None
    """
    if hasattr(request, 'headers'):
        if hasattr(request.headers, 'get'):
            return request.headers.get('Referer')
        elif isinstance(request.headers, dict):
            return request.headers.get('Referer')
    return None


def anonymize_ip(ip_address: str) -> str:
    """
    Anonymize IP address for privacy (last octet for IPv4, last 64 bits for IPv6)
    
    Args:
        ip_address: IP address to anonymize
        
    Returns:
        Anonymized IP address (returns original if invalid format)
    """
    if not ip_address or not isinstance(ip_address, str):
        return ip_address or ""
    
    ip_address = ip_address.strip()
    if not ip_address:
        return ""
    
    # Try IPv4 format (e.g., 192.168.1.100)
    if '.' in ip_address and ':' not in ip_address:
        parts = ip_address.split('.')
        if len(parts) == 4:
            # Validate each part is numeric
            try:
                for part in parts:
                    int(part)
                return '.'.join(parts[:3]) + '.0'
            except ValueError:
                # Invalid IPv4 format, return original
                return ip_address
    
    # Try IPv6 format (e.g., 2001:0db8:85a3:0000:0000:8a2e:0370:7334)
    elif ':' in ip_address:
        # Handle compressed IPv6 (e.g., ::1 or 2001::1)
        if '::' in ip_address:
            # Don't anonymize compressed IPv6 (too complex)
            return ip_address
        parts = ip_address.split(':')
        if len(parts) >= 4:
            return ':'.join(parts[:4]) + ':0000:0000:0000:0000'
    
    # Unknown format, return original
    return ip_address
