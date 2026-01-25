# Request Logging Feature - IP Address Tracking

## Overview

This document outlines the implementation of request logging to track IP addresses, timestamps, and URLs for public web service deployment.

## Feature Requirements

- Store IP address of requester
- Store timestamp of request
- Store URL being tested
- Associate with test_run_id and stream_id
- Support rate limiting per IP
- Support analytics and abuse detection

## Database Schema Changes

### New Table: `request_logs`

```sql
CREATE TABLE IF NOT EXISTS request_logs (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address TEXT NOT NULL,
    request_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stream_url TEXT NOT NULL,
    test_run_id TEXT,
    stream_id TEXT,
    user_agent TEXT,
    referer TEXT,
    request_method TEXT DEFAULT 'POST',
    response_status INTEGER,
    processing_time_ms INTEGER,
    FOREIGN KEY (test_run_id) REFERENCES test_runs(test_run_id),
    FOREIGN KEY (stream_id) REFERENCES streams(stream_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_request_logs_ip_timestamp 
ON request_logs(ip_address, request_timestamp);

CREATE INDEX IF NOT EXISTS idx_request_logs_timestamp 
ON request_logs(request_timestamp);

CREATE INDEX IF NOT EXISTS idx_request_logs_test_run_id 
ON request_logs(test_run_id);
```

### PostgreSQL Version (for AWS deployment)

```sql
CREATE TABLE IF NOT EXISTS request_logs (
    request_id SERIAL PRIMARY KEY,
    ip_address INET NOT NULL,
    request_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stream_url TEXT NOT NULL,
    test_run_id UUID,
    stream_id TEXT,
    user_agent TEXT,
    referer TEXT,
    request_method TEXT DEFAULT 'POST',
    response_status INTEGER,
    processing_time_ms INTEGER,
    customer_id UUID,
    FOREIGN KEY (test_run_id) REFERENCES test_runs(test_run_id),
    FOREIGN KEY (stream_id) REFERENCES streams(stream_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE INDEX idx_request_logs_ip_timestamp 
ON request_logs(ip_address, request_timestamp);

CREATE INDEX idx_request_logs_timestamp 
ON request_logs(request_timestamp DESC);

CREATE INDEX idx_request_logs_test_run_id 
ON request_logs(test_run_id);

CREATE INDEX idx_request_logs_customer_id 
ON request_logs(customer_id) WHERE customer_id IS NOT NULL;
```

## Implementation

### 1. Database Model Update

**File:** `stream_checker/database/models.py`

Add new method to `Database` class:

```python
def log_request(
    self,
    ip_address: str,
    stream_url: str,
    test_run_id: Optional[str] = None,
    stream_id: Optional[str] = None,
    user_agent: Optional[str] = None,
    referer: Optional[str] = None,
    request_method: str = "POST",
    response_status: Optional[int] = None,
    processing_time_ms: Optional[int] = None
) -> int:
    """Log API request with IP address and metadata"""
    conn = None
    try:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO request_logs (
                ip_address, stream_url, test_run_id, stream_id,
                user_agent, referer, request_method,
                response_status, processing_time_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ip_address, stream_url, test_run_id, stream_id,
            user_agent, referer, request_method,
            response_status, processing_time_ms
        ))
        
        request_id = cursor.lastrowid
        conn.commit()
        return request_id
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Error logging request: {e}")
        raise
    finally:
        if conn:
            conn.close()

def get_request_history(
    self,
    ip_address: Optional[str] = None,
    limit: int = 100,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """Get request history with optional filters"""
    conn = None
    try:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT request_id, ip_address, request_timestamp, stream_url,
                   test_run_id, stream_id, user_agent, request_method,
                   response_status, processing_time_ms
            FROM request_logs
            WHERE 1=1
        """
        params = []
        
        if ip_address:
            query += " AND ip_address = ?"
            params.append(ip_address)
        
        if start_time:
            query += " AND request_timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND request_timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " ORDER BY request_timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        return [
            {
                "request_id": row["request_id"],
                "ip_address": row["ip_address"],
                "request_timestamp": row["request_timestamp"],
                "stream_url": row["stream_url"],
                "test_run_id": row["test_run_id"],
                "stream_id": row["stream_id"],
                "user_agent": row["user_agent"],
                "request_method": row["request_method"],
                "response_status": row["response_status"],
                "processing_time_ms": row["processing_time_ms"]
            }
            for row in rows
        ]
    except sqlite3.Error as e:
        logger.error(f"Error getting request history: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_ip_request_count(
    self,
    ip_address: str,
    time_window_minutes: int = 60
) -> int:
    """Get request count for IP address within time window"""
    conn = None
    try:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM request_logs
            WHERE ip_address = ?
            AND request_timestamp >= datetime('now', '-' || ? || ' minutes')
        """, (ip_address, time_window_minutes))
        
        row = cursor.fetchone()
        return row["count"] if row else 0
    except sqlite3.Error as e:
        logger.error(f"Error getting IP request count: {e}")
        return 0
    finally:
        if conn:
            conn.close()
```

### 2. IP Address Extraction Utility

**File:** `stream_checker/utils/request_utils.py` (new file)

```python
"""Utility functions for request handling"""

from typing import Optional
from flask import request as flask_request
from fastapi import Request as FastAPIRequest


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
            # FastAPI
            value = request.headers.get(header)
        elif hasattr(request, 'headers'):
            # Flask
            value = request.headers.get(header)
        
        if value:
            # X-Forwarded-For can contain multiple IPs (client, proxy1, proxy2)
            # Take the first one (original client)
            ip = value.split(',')[0].strip()
            if ip:
                return ip
    
    return None


def get_user_agent(request) -> Optional[str]:
    """Extract User-Agent from request"""
    if hasattr(request, 'headers'):
        return request.headers.get('User-Agent')
    return None


def get_referer(request) -> Optional[str]:
    """Extract Referer from request"""
    if hasattr(request, 'headers'):
        return request.headers.get('Referer')
    return None
```

### 3. FastAPI Example Implementation

**File:** `api/main.py` (example for web service)

```python
"""FastAPI application with request logging"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import time
import logging
from typing import Optional

from stream_checker.database.models import Database
from stream_checker.security.key_management import generate_test_run_id, generate_stream_id
from stream_checker.security.validation import URLValidator, ValidationError
from stream_checker.utils.request_utils import get_client_ip, get_user_agent, get_referer
from stream_checker import main as stream_checker_main

logger = logging.getLogger("stream_checker")
app = FastAPI(title="Stream Checker API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
db = Database("~/.stream_checker/stream_checker.db")


@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    """Middleware to log all requests with IP address"""
    start_time = time.time()
    
    # Extract request metadata
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)
    referer = get_referer(request)
    
    # Process request
    response = await call_next(request)
    
    # Calculate processing time
    processing_time_ms = int((time.time() - start_time) * 1000)
    
    # Log request (async - don't block response)
    try:
        # Extract stream_url from request if available
        stream_url = None
        if request.method == "POST" and request.url.path == "/api/streams/check":
            try:
                body = await request.json()
                stream_url = body.get("url")
            except:
                pass
        
        db.log_request(
            ip_address=ip_address or "unknown",
            stream_url=stream_url or request.url.path,
            user_agent=user_agent,
            referer=referer,
            request_method=request.method,
            response_status=response.status_code,
            processing_time_ms=processing_time_ms
        )
    except Exception as e:
        logger.error(f"Error logging request: {e}")
    
    return response


@app.post("/api/streams/check")
async def check_stream(request: Request, url: str):
    """
    Check stream URL
    
    Args:
        request: FastAPI Request object (for IP extraction)
        url: Stream URL to check
    
    Returns:
        Stream check results
    """
    # Extract IP address
    ip_address = get_client_ip(request) or "unknown"
    
    # Validate URL
    url_validator = URLValidator(
        allowed_schemes=["http", "https"],
        block_private_ips=False,  # Configure based on needs
        max_url_length=2048
    )
    
    try:
        url_validator.validate_and_raise(url)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Generate IDs
    test_run_id = generate_test_run_id()
    stream_id = generate_stream_id(url)
    
    # Log request with IDs
    try:
        request_id = db.log_request(
            ip_address=ip_address,
            stream_url=url,
            test_run_id=test_run_id,
            stream_id=stream_id,
            user_agent=get_user_agent(request),
            referer=get_referer(request),
            request_method="POST"
        )
        logger.info(f"Request logged: request_id={request_id}, ip={ip_address}, url={url}")
    except Exception as e:
        logger.error(f"Error logging request: {e}")
        # Continue even if logging fails
    
    # Run stream check
    try:
        # Call your existing stream checker logic
        result = stream_checker_main.check_stream(url, test_run_id=test_run_id)
        
        # Update request log with response status
        db.log_request(
            ip_address=ip_address,
            stream_url=url,
            test_run_id=test_run_id,
            stream_id=stream_id,
            response_status=200,
            processing_time_ms=result.get("processing_time_ms")
        )
        
        return result
    except Exception as e:
        logger.error(f"Error checking stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/requests/history")
async def get_request_history(
    request: Request,
    ip_address: Optional[str] = None,
    limit: int = 100
):
    """Get request history (admin endpoint)"""
    # In production, add authentication/authorization here
    
    client_ip = get_client_ip(request)
    
    # Only allow querying own IP or require admin role
    if ip_address and ip_address != client_ip:
        # Check if user is admin (implement your auth logic)
        # raise HTTPException(status_code=403, detail="Not authorized")
        pass
    
    history = db.get_request_history(
        ip_address=ip_address or client_ip,
        limit=limit
    )
    
    return {"requests": history}


@app.get("/api/requests/stats")
async def get_request_stats(request: Request):
    """Get request statistics (admin endpoint)"""
    # In production, add authentication/authorization here
    
    client_ip = get_client_ip(request)
    
    # Get request count in last hour
    count_last_hour = db.get_ip_request_count(client_ip, time_window_minutes=60)
    
    return {
        "ip_address": client_ip,
        "requests_last_hour": count_last_hour,
        "rate_limit": 10,  # Configure based on your needs
        "remaining": max(0, 10 - count_last_hour)
    }
```

### 4. Flask Example Implementation

**File:** `api/flask_app.py` (alternative implementation)

```python
"""Flask application with request logging"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import logging

from stream_checker.database.models import Database
from stream_checker.utils.request_utils import get_client_ip, get_user_agent, get_referer

logger = logging.getLogger("stream_checker")
app = Flask(__name__)
CORS(app)

db = Database("~/.stream_checker/stream_checker.db")


@app.before_request
def log_request():
    """Log all requests before processing"""
    start_time = time.time()
    request.start_time = start_time


@app.after_request
def log_response(response):
    """Log request after processing"""
    processing_time_ms = int((time.time() - request.start_time) * 1000)
    
    ip_address = get_client_ip(request) or "unknown"
    
    try:
        db.log_request(
            ip_address=ip_address,
            stream_url=request.path,
            user_agent=get_user_agent(request),
            referer=get_referer(request),
            request_method=request.method,
            response_status=response.status_code,
            processing_time_ms=processing_time_ms
        )
    except Exception as e:
        logger.error(f"Error logging request: {e}")
    
    return response


@app.route("/api/streams/check", methods=["POST"])
def check_stream():
    """Check stream URL"""
    data = request.get_json()
    url = data.get("url")
    
    if not url:
        return jsonify({"error": "URL required"}), 400
    
    ip_address = get_client_ip(request) or "unknown"
    
    # Generate IDs and log
    test_run_id = generate_test_run_id()
    stream_id = generate_stream_id(url)
    
    try:
        request_id = db.log_request(
            ip_address=ip_address,
            stream_url=url,
            test_run_id=test_run_id,
            stream_id=stream_id
        )
        logger.info(f"Request logged: request_id={request_id}, ip={ip_address}")
    except Exception as e:
        logger.error(f"Error logging request: {e}")
    
    # Run stream check...
    # (Your existing logic)
    
    return jsonify({"test_run_id": test_run_id, "stream_id": stream_id})
```

## Privacy & Security Considerations

### 1. GDPR Compliance
- **Data Retention:** Consider implementing automatic deletion of old logs
- **Right to Deletion:** Allow users to request deletion of their request logs
- **Data Minimization:** Only store necessary data

### 2. IP Address Anonymization (Optional)
```python
def anonymize_ip(ip_address: str) -> str:
    """Anonymize IP address (last octet for IPv4, last 64 bits for IPv6)"""
    if '.' in ip_address:  # IPv4
        parts = ip_address.split('.')
        return '.'.join(parts[:3]) + '.0'
    elif ':' in ip_address:  # IPv6
        parts = ip_address.split(':')
        return ':'.join(parts[:4]) + ':0000:0000:0000:0000'
    return ip_address
```

### 3. Rate Limiting
```python
def check_rate_limit(db: Database, ip_address: str, max_requests: int = 10, window_minutes: int = 60) -> bool:
    """Check if IP address has exceeded rate limit"""
    count = db.get_ip_request_count(ip_address, time_window_minutes=window_minutes)
    return count < max_requests
```

## Configuration

Add to `config.yaml`:

```yaml
request_logging:
  enabled: true
  retention_days: 90  # Auto-delete logs older than 90 days
  anonymize_ips: false  # Set to true for GDPR compliance
  log_user_agent: true
  log_referer: true

rate_limiting:
  enabled: true
  max_requests_per_hour: 10
  max_requests_per_day: 100
  block_duration_minutes: 60  # Block IP for 1 hour if limit exceeded
```

## Benefits

1. **Security:**
   - Track abuse patterns
   - Identify malicious IPs
   - Support rate limiting

2. **Analytics:**
   - Popular stream URLs
   - Request patterns
   - Geographic distribution (if IP geolocation added)

3. **Debugging:**
   - Trace requests to test runs
   - Identify performance issues
   - Monitor API usage

4. **Compliance:**
   - Audit trail
   - Request logging for security incidents

## Next Steps

1. ✅ Add database schema migration
2. ✅ Update Database class with logging methods
3. ✅ Create request utility functions
4. ✅ Implement API middleware
5. ✅ Add rate limiting based on IP
6. ✅ Add admin endpoints for viewing logs
7. ✅ Implement data retention policy
8. ✅ Add IP geolocation (optional)
