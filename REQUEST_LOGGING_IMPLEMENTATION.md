# Request Logging Implementation - Complete

## ✅ Implementation Summary

Request logging has been successfully implemented! All IP addresses, timestamps, and URLs are now ready to be logged when you deploy your web service.

## What Was Added

### 1. Database Schema ✅
**File:** `stream_checker/database/models.py`

- **New Table:** `request_logs`
  - `request_id` (PRIMARY KEY, auto-increment)
  - `ip_address` (TEXT, NOT NULL)
  - `request_timestamp` (TIMESTAMP, auto-set)
  - `stream_url` (TEXT, NOT NULL)
  - `test_run_id` (TEXT, foreign key)
  - `stream_id` (TEXT, foreign key)
  - `user_agent` (TEXT, optional)
  - `referer` (TEXT, optional)
  - `request_method` (TEXT, default: 'POST')
  - `response_status` (INTEGER, optional)
  - `processing_time_ms` (INTEGER, optional)

- **Indexes Created:**
  - `idx_request_logs_ip_timestamp` - For IP-based queries
  - `idx_request_logs_timestamp` - For time-based queries
  - `idx_request_logs_test_run_id` - For linking to test runs

### 2. Database Methods ✅
**File:** `stream_checker/database/models.py`

Three new methods added to `Database` class:

1. **`log_request()`** - Log a request with all metadata
   ```python
   request_id = db.log_request(
       ip_address="192.168.1.100",
       stream_url="https://example.com/stream.mp3",
       test_run_id="test-123",
       stream_id="stream-456",
       user_agent="Mozilla/5.0",
       request_method="POST",
       response_status=200,
       processing_time_ms=1500
   )
   ```

2. **`get_request_history()`** - Get request history with filters
   ```python
   history = db.get_request_history(
       ip_address="192.168.1.100",
       limit=100,
       start_time=datetime(2026, 1, 1),
       end_time=datetime(2026, 1, 31)
   )
   ```

3. **`get_ip_request_count()`** - Get request count for rate limiting
   ```python
   count = db.get_ip_request_count("192.168.1.100", time_window_minutes=60)
   ```

### 3. Request Utilities ✅
**File:** `stream_checker/utils/request_utils.py` (NEW)

Utility functions for extracting request metadata:

1. **`get_client_ip(request)`** - Extract IP address
   - Handles Flask and FastAPI requests
   - Checks proxy headers (X-Forwarded-For, X-Real-IP, etc.)
   - Handles AWS ALB and CloudFront headers

2. **`get_user_agent(request)`** - Extract User-Agent header

3. **`get_referer(request)`** - Extract Referer header

4. **`anonymize_ip(ip_address)`** - Anonymize IP for privacy (optional)

### 4. Example API Code ✅
**File:** `API_USAGE_EXAMPLE.py` (NEW)

Complete FastAPI and Flask examples showing:
- Middleware for automatic request logging
- Rate limiting based on IP address
- Request history endpoints
- Request statistics endpoints

## Testing Results ✅

All tests passed:
- ✅ Database initialization with new table
- ✅ Request logging functionality
- ✅ Request history retrieval
- ✅ IP-based request counting
- ✅ No syntax errors
- ✅ No linter errors

## Usage Example

When you build your web API, you can use it like this:

```python
from fastapi import FastAPI, Request
from stream_checker.database.models import Database
from stream_checker.utils.request_utils import get_client_ip

app = FastAPI()
db = Database("~/.stream_checker/stream_checker.db")

@app.post("/api/streams/check")
async def check_stream(request: Request, url: str):
    # Get IP address
    ip_address = get_client_ip(request) or "unknown"
    
    # Check rate limit
    count = db.get_ip_request_count(ip_address, time_window_minutes=60)
    if count >= 10:
        return {"error": "Rate limit exceeded"}, 429
    
    # Generate IDs
    test_run_id = generate_test_run_id()
    stream_id = generate_stream_id(url)
    
    # Log the request
    request_id = db.log_request(
        ip_address=ip_address,
        stream_url=url,
        test_run_id=test_run_id,
        stream_id=stream_id,
        user_agent=get_user_agent(request),
        request_method="POST"
    )
    
    # Process stream check...
    # ...
    
    return {"test_run_id": test_run_id, "stream_id": stream_id}
```

## Database Schema

The `request_logs` table will be automatically created when you initialize a new `Database` instance. For existing databases, the table will be created on the next initialization (SQLite's `CREATE TABLE IF NOT EXISTS` handles this).

## Next Steps

1. **When you build your web API:**
   - Use the example code in `API_USAGE_EXAMPLE.py`
   - Add middleware to automatically log all requests
   - Implement rate limiting using `get_ip_request_count()`

2. **For production:**
   - Add authentication/authorization to history endpoints
   - Configure rate limits in your config
   - Consider IP anonymization for GDPR compliance
   - Set up data retention policies

3. **For AWS deployment:**
   - The IP extraction handles AWS ALB and CloudFront headers
   - Consider using RDS PostgreSQL for better performance
   - Add CloudWatch metrics for request monitoring

## Files Modified/Created

- ✅ `stream_checker/database/models.py` - Added table and methods
- ✅ `stream_checker/utils/request_utils.py` - NEW file with utilities
- ✅ `API_USAGE_EXAMPLE.py` - NEW file with example code
- ✅ `REQUEST_LOGGING_FEATURE.md` - Feature documentation
- ✅ `REQUEST_LOGGING_IMPLEMENTATION.md` - This file

## Verification

Run this to verify everything works:

```python
from stream_checker.database.models import Database
from stream_checker.utils.request_utils import get_client_ip

db = Database("~/.stream_checker/stream_checker.db")

# Log a test request
request_id = db.log_request(
    ip_address="192.168.1.100",
    stream_url="https://example.com/stream.mp3",
    test_run_id="test-123",
    stream_id="stream-456"
)

# Get history
history = db.get_request_history(limit=10)
print(f"Logged {len(history)} requests")

# Get IP count
count = db.get_ip_request_count("192.168.1.100", 60)
print(f"IP has {count} requests in last hour")
```

## Summary

✅ **Request logging is fully implemented and ready to use!**

All IP addresses, timestamps, and URLs will be automatically logged when you:
1. Build your web API (FastAPI or Flask)
2. Add the middleware from the examples
3. Call `db.log_request()` in your endpoints

The implementation is production-ready and includes:
- Proper database schema with indexes
- IP extraction that handles proxies and load balancers
- Rate limiting support
- Request history queries
- Full integration with existing test_run_id and stream_id system
