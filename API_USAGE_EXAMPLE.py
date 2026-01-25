"""
Example API implementation showing how to use request logging

This is a reference implementation for when you build your web API.
You can use this as a starting point for FastAPI or Flask.
"""

# FastAPI Example
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import time
import logging

from stream_checker.database.models import Database
from stream_checker.security.key_management import generate_test_run_id, generate_stream_id
from stream_checker.security.validation import URLValidator, ValidationError
from stream_checker.utils.request_utils import get_client_ip, get_user_agent, get_referer

logger = logging.getLogger("stream_checker")
app = FastAPI(title="Stream Checker API")

# Initialize database
db = Database("~/.stream_checker/stream_checker.db")


@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    """Middleware to log all requests with IP address"""
    start_time = time.time()
    
    # Extract request metadata
    ip_address = get_client_ip(request) or "unknown"
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
            ip_address=ip_address,
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
    
    # Check rate limiting (example: 10 requests per hour)
    request_count = db.get_ip_request_count(ip_address, time_window_minutes=60)
    if request_count >= 10:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {request_count} requests in the last hour"
        )
    
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
    
    # Log request with IDs (before processing)
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
    
    # Run stream check (your existing logic here)
    # result = stream_checker_main.check_stream(url, test_run_id=test_run_id)
    
    # For this example, return a simple response
    return {
        "test_run_id": test_run_id,
        "stream_id": stream_id,
        "stream_url": url,
        "status": "processing"
    }


@app.get("/api/requests/history")
async def get_request_history(
    request: Request,
    ip_address: str = None,
    limit: int = 100
):
    """
    Get request history (admin endpoint)
    
    Args:
        request: FastAPI Request object
        ip_address: Filter by IP address (optional)
        limit: Maximum number of records to return
    
    Returns:
        Request history
    """
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
    """
    Get request statistics for current IP
    
    Args:
        request: FastAPI Request object
    
    Returns:
        Request statistics
    """
    client_ip = get_client_ip(request) or "unknown"
    
    # Get request count in last hour
    count_last_hour = db.get_ip_request_count(client_ip, time_window_minutes=60)
    count_last_day = db.get_ip_request_count(client_ip, time_window_minutes=1440)
    
    return {
        "ip_address": client_ip,
        "requests_last_hour": count_last_hour,
        "requests_last_day": count_last_day,
        "rate_limit_per_hour": 10,  # Configure based on your needs
        "remaining_this_hour": max(0, 10 - count_last_hour)
    }


# Flask Example (alternative)
"""
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
    request.start_time = time.time()


@app.after_request
def log_response(response):
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
    data = request.get_json()
    url = data.get("url")
    
    if not url:
        return jsonify({"error": "URL required"}), 400
    
    ip_address = get_client_ip(request) or "unknown"
    
    # Check rate limiting
    count = db.get_ip_request_count(ip_address, time_window_minutes=60)
    if count >= 10:
        return jsonify({"error": "Rate limit exceeded"}), 429
    
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
    return jsonify({
        "test_run_id": test_run_id,
        "stream_id": stream_id,
        "status": "processing"
    })
"""
