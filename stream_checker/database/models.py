"""Database models and schema"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger("stream_checker")


class Database:
    """SQLite database manager"""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema"""
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Streams table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS streams (
                    stream_id TEXT PRIMARY KEY,
                    url TEXT UNIQUE NOT NULL,
                    name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_tested TIMESTAMP,
                    test_count INTEGER DEFAULT 0
                )
            """)
            
            # Test runs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_runs (
                    test_run_id TEXT PRIMARY KEY,
                    stream_id TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    phase INTEGER NOT NULL,
                    results TEXT,
                    FOREIGN KEY (stream_id) REFERENCES streams(stream_id)
                )
            """)
            
            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_test_runs_stream_timestamp 
                ON test_runs(stream_id, timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_test_runs_timestamp 
                ON test_runs(timestamp)
            """)
            
            # Request logs table
            cursor.execute("""
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
                )
            """)
            
            # Create indexes for request_logs
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_request_logs_ip_timestamp 
                ON request_logs(ip_address, request_timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_request_logs_timestamp 
                ON request_logs(request_timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_request_logs_test_run_id 
                ON request_logs(test_run_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_request_logs_stream_id 
                ON request_logs(stream_id)
            """)
            
            # Listening sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS listening_sessions (
                    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL,
                    stream_url TEXT NOT NULL,
                    user_agent TEXT,
                    start_timestamp TIMESTAMP NOT NULL,
                    end_timestamp TIMESTAMP,
                    listening_time_seconds REAL NOT NULL,
                    action_type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for listening_sessions
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_listening_sessions_ip_timestamp 
                ON listening_sessions(ip_address, start_timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_listening_sessions_timestamp 
                ON listening_sessions(start_timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_listening_sessions_stream_url 
                ON listening_sessions(stream_url)
            """)
            
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error initializing database: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn
    
    @contextmanager
    def _get_connection_context(self):
        """Context manager for database connections"""
        conn = None
        try:
            conn = self.get_connection()
            yield conn
        except sqlite3.Error:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def add_stream(self, stream_id: str, url: str, name: Optional[str] = None):
        """
        Add or update stream
        
        Args:
            stream_id: Stream ID
            url: Stream URL
            name: Optional stream name
            
        Raises:
            ValueError: If required parameters are invalid
        """
        # Validate required parameters
        if not stream_id or not isinstance(stream_id, str):
            raise ValueError("stream_id must be a non-empty string")
        if not url or not isinstance(url, str):
            raise ValueError("url must be a non-empty string")
        
        with self._get_connection_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO streams (stream_id, url, name, last_tested)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (stream_id, url, name))
            conn.commit()
    
    def update_stream_test_count(self, stream_id: str):
        """
        Increment test count for stream
        
        Args:
            stream_id: Stream ID to update
            
        Raises:
            ValueError: If stream_id is invalid
        """
        # Validate stream_id
        if not stream_id or not isinstance(stream_id, str):
            raise ValueError("stream_id must be a non-empty string")
        
        with self._get_connection_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE streams 
                SET test_count = test_count + 1,
                    last_tested = CURRENT_TIMESTAMP
                WHERE stream_id = ?
            """, (stream_id,))
            conn.commit()
    
    def add_test_run(
        self,
        test_run_id: str,
        stream_id: str,
        phase: int,
        results: Dict[str, Any]
    ):
        """
        Add or update test run result
        
        Args:
            test_run_id: Test run ID
            stream_id: Stream ID
            phase: Phase number (1-4)
            results: Test results dictionary
            
        Raises:
            ValueError: If parameters are invalid
        """
        # Validate parameters
        if not test_run_id or not isinstance(test_run_id, str):
            raise ValueError("test_run_id must be a non-empty string")
        if not stream_id or not isinstance(stream_id, str):
            raise ValueError("stream_id must be a non-empty string")
        if not isinstance(phase, int) or phase < 1 or phase > 4:
            raise ValueError("phase must be an integer between 1 and 4")
        if not isinstance(results, dict):
            raise ValueError("results must be a dictionary")
        
        # Validate JSON serialization before database operation
        try:
            json_str = json.dumps(results)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Results cannot be serialized to JSON: {e}")
        
        with self._get_connection_context() as conn:
            cursor = conn.cursor()
            
            # Check if test_run_id already exists
            cursor.execute("""
                SELECT phase FROM test_runs WHERE test_run_id = ?
            """, (test_run_id,))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing record (use highest phase number)
                existing_phase = existing["phase"]
                if phase > existing_phase:
                    cursor.execute("""
                        UPDATE test_runs 
                        SET phase = ?, results = ?
                        WHERE test_run_id = ?
                    """, (phase, json_str, test_run_id))
                else:
                    # Update results but keep the higher phase number and update timestamp
                    cursor.execute("""
                        UPDATE test_runs 
                        SET results = ?, timestamp = CURRENT_TIMESTAMP
                        WHERE test_run_id = ?
                    """, (json_str, test_run_id))
            else:
                # Insert new record
                cursor.execute("""
                    INSERT INTO test_runs (test_run_id, stream_id, phase, results)
                    VALUES (?, ?, ?, ?)
                """, (test_run_id, stream_id, phase, json_str))
            
            conn.commit()
    
    def get_stream_history(self, stream_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get test run history for a stream
        
        Args:
            stream_id: Stream ID to get history for
            limit: Maximum number of records to return (1-10000, default: 10)
            
        Returns:
            List of test run dictionaries
            
        Raises:
            ValueError: If limit is invalid
        """
        # Validate limit
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        if limit > 10000:
            raise ValueError("limit cannot exceed 10000")
        
        # Validate stream_id
        if not stream_id or not isinstance(stream_id, str):
            raise ValueError("stream_id must be a non-empty string")
        
        try:
            with self._get_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT test_run_id, timestamp, phase, results
                    FROM test_runs
                    WHERE stream_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (stream_id, limit))
                
                rows = cursor.fetchall()
                
                return [
                    {
                        "test_run_id": row["test_run_id"],
                        "timestamp": row["timestamp"],
                        "phase": row["phase"],
                        "results": json.loads(row["results"])
                    }
                    for row in rows
                ]
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Error getting stream history: {e}")
            return []
    
    def get_stream_info(self, stream_id: str) -> Optional[Dict[str, Any]]:
        """
        Get stream information
        
        Args:
            stream_id: Stream ID to get information for
            
        Returns:
            Dictionary with stream information or None if not found
            
        Raises:
            ValueError: If stream_id is invalid
        """
        # Validate stream_id
        if not stream_id or not isinstance(stream_id, str):
            raise ValueError("stream_id must be a non-empty string")
        
        try:
            with self._get_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT stream_id, url, name, created_at, last_tested, test_count
                    FROM streams
                    WHERE stream_id = ?
                """, (stream_id,))
                
                row = cursor.fetchone()
                
                if row:
                    return {
                        "stream_id": row["stream_id"],
                        "url": row["url"],
                        "name": row["name"],
                        "created_at": row["created_at"],
                        "last_tested": row["last_tested"],
                        "test_count": row["test_count"]
                    }
                return None
        except sqlite3.Error as e:
            logger.error(f"Error getting stream info: {e}")
            return None
    
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
        """
        Log API request with IP address and metadata
        
        Args:
            ip_address: Client IP address
            stream_url: Stream URL being tested
            test_run_id: Associated test run ID (optional)
            stream_id: Associated stream ID (optional)
            user_agent: User-Agent header (optional)
            referer: Referer header (optional)
            request_method: HTTP method (default: POST)
            response_status: HTTP response status code (optional)
            processing_time_ms: Request processing time in milliseconds (optional)
            
        Returns:
            request_id of the logged request
            
        Raises:
            ValueError: If required parameters are invalid
            sqlite3.Error: If database operation fails
        """
        # Validate required parameters
        if not ip_address or not isinstance(ip_address, str):
            raise ValueError("ip_address must be a non-empty string")
        if not stream_url or not isinstance(stream_url, str):
            raise ValueError("stream_url must be a non-empty string")
        if not request_method or not isinstance(request_method, str):
            raise ValueError("request_method must be a non-empty string")
        
        # Validate optional parameters
        if response_status is not None and not isinstance(response_status, int):
            raise ValueError("response_status must be an integer or None")
        if processing_time_ms is not None and not isinstance(processing_time_ms, int):
            raise ValueError("processing_time_ms must be an integer or None")
        
        with self._get_connection_context() as conn:
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
    
    def get_request_history(
        self,
        ip_address: Optional[str] = None,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get request history with optional filters
        
        Args:
            ip_address: Filter by IP address (optional)
            limit: Maximum number of records to return (1-10000, default: 100)
            start_time: Filter requests after this time (optional)
            end_time: Filter requests before this time (optional)
            
        Returns:
            List of request dictionaries
            
        Raises:
            ValueError: If limit is invalid
        """
        # Validate limit
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        if limit > 10000:
            raise ValueError("limit cannot exceed 10000")
        
        # Validate time range
        if start_time and end_time and start_time > end_time:
            raise ValueError("start_time must be before end_time")
        
        try:
            with self._get_connection_context() as conn:
                cursor = conn.cursor()
                
                # Build query safely with parameterized conditions
                query_parts = [
                    "SELECT request_id, ip_address, request_timestamp, stream_url",
                    "test_run_id, stream_id, user_agent, request_method",
                    "response_status, processing_time_ms",
                    "FROM request_logs",
                    "WHERE 1=1"
                ]
                params = []
                
                if ip_address:
                    if not isinstance(ip_address, str) or not ip_address.strip():
                        raise ValueError("ip_address must be a non-empty string")
                    query_parts.append("AND ip_address = ?")
                    params.append(ip_address.strip())
                
                if start_time:
                    if not isinstance(start_time, datetime):
                        raise ValueError("start_time must be a datetime object")
                    query_parts.append("AND request_timestamp >= ?")
                    params.append(start_time.isoformat())
                
                if end_time:
                    if not isinstance(end_time, datetime):
                        raise ValueError("end_time must be a datetime object")
                    query_parts.append("AND request_timestamp <= ?")
                    params.append(end_time.isoformat())
                
                query_parts.append("ORDER BY request_timestamp DESC LIMIT ?")
                params.append(limit)
                
                query = " ".join(query_parts)
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
    
    def get_ip_request_count(
        self,
        ip_address: str,
        time_window_minutes: int = 60
    ) -> int:
        """
        Get request count for IP address within time window
        
        Args:
            ip_address: IP address to check
            time_window_minutes: Time window in minutes (1-1440, default: 60)
            
        Returns:
            Number of requests from this IP in the time window
            
        Raises:
            ValueError: If parameters are invalid
        """
        # Validate parameters
        if not ip_address or not isinstance(ip_address, str):
            raise ValueError("ip_address must be a non-empty string")
        if not isinstance(time_window_minutes, int) or time_window_minutes < 1:
            raise ValueError("time_window_minutes must be a positive integer")
        if time_window_minutes > 1440:  # 24 hours
            raise ValueError("time_window_minutes cannot exceed 1440 (24 hours)")
        
        try:
            with self._get_connection_context() as conn:
                cursor = conn.cursor()
                
                # Use CAST to ensure time_window_minutes is treated as integer
                # This prevents SQL injection and ensures correct datetime calculation
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM request_logs
                    WHERE ip_address = ?
                    AND request_timestamp >= datetime('now', '-' || CAST(? AS TEXT) || ' minutes')
                """, (ip_address, time_window_minutes))
                
                row = cursor.fetchone()
                if row:
                    return int(row["count"])
                return 0
        except sqlite3.Error as e:
            logger.error(f"Error getting IP request count: {e}")
            return 0
    
    def log_listening_session(
        self,
        ip_address: str,
        stream_url: str,
        start_timestamp: datetime,
        end_timestamp: datetime,
        listening_time_seconds: float,
        action_type: str,
        user_agent: Optional[str] = None
    ) -> int:
        """
        Log a listening session (play to pause/stop, or unpause to pause/stop)
        
        Args:
            ip_address: Client IP address
            stream_url: Stream URL being listened to
            start_timestamp: When listening started (play or unpause)
            end_timestamp: When listening ended (pause or stop)
            listening_time_seconds: Duration of listening in seconds
            action_type: Type of action that ended listening ('pause' or 'stop')
            user_agent: User-Agent header (optional)
            
        Returns:
            session_id of the logged session
            
        Raises:
            ValueError: If required parameters are invalid
            sqlite3.Error: If database operation fails
        """
        # Validate required parameters
        if not ip_address or not isinstance(ip_address, str):
            raise ValueError("ip_address must be a non-empty string")
        if not stream_url or not isinstance(stream_url, str):
            raise ValueError("stream_url must be a non-empty string")
        if not isinstance(start_timestamp, datetime):
            raise ValueError("start_timestamp must be a datetime object")
        if not isinstance(end_timestamp, datetime):
            raise ValueError("end_timestamp must be a datetime object")
        if not isinstance(listening_time_seconds, (int, float)) or listening_time_seconds < 0:
            raise ValueError("listening_time_seconds must be a non-negative number")
        if action_type not in ('pause', 'stop'):
            raise ValueError("action_type must be 'pause' or 'stop'")
        
        with self._get_connection_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO listening_sessions (
                    ip_address, stream_url, user_agent,
                    start_timestamp, end_timestamp,
                    listening_time_seconds, action_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                ip_address,
                stream_url,
                user_agent,
                start_timestamp.isoformat(),
                end_timestamp.isoformat(),
                listening_time_seconds,
                action_type
            ))
            
            session_id = cursor.lastrowid
            conn.commit()
            return session_id
    
    def get_listening_history(
        self,
        ip_address: Optional[str] = None,
        stream_url: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get listening session history with optional filters
        
        Args:
            ip_address: Filter by IP address (optional)
            stream_url: Filter by stream URL (optional)
            limit: Maximum number of records to return (1-10000, default: 100)
            
        Returns:
            List of listening session dictionaries
            
        Raises:
            ValueError: If limit is invalid
        """
        # Validate limit
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        if limit > 10000:
            raise ValueError("limit cannot exceed 10000")
        
        try:
            with self._get_connection_context() as conn:
                cursor = conn.cursor()
                
                query_parts = [
                    "SELECT session_id, ip_address, stream_url, user_agent,",
                    "start_timestamp, end_timestamp, listening_time_seconds, action_type, created_at",
                    "FROM listening_sessions",
                    "WHERE 1=1"
                ]
                params = []
                
                if ip_address:
                    if not isinstance(ip_address, str) or not ip_address.strip():
                        raise ValueError("ip_address must be a non-empty string")
                    query_parts.append("AND ip_address = ?")
                    params.append(ip_address.strip())
                
                if stream_url:
                    if not isinstance(stream_url, str) or not stream_url.strip():
                        raise ValueError("stream_url must be a non-empty string")
                    query_parts.append("AND stream_url = ?")
                    params.append(stream_url.strip())
                
                query_parts.append("ORDER BY start_timestamp DESC LIMIT ?")
                params.append(limit)
                
                query = " ".join(query_parts)
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                return [
                    {
                        "session_id": row["session_id"],
                        "ip_address": row["ip_address"],
                        "stream_url": row["stream_url"],
                        "user_agent": row["user_agent"],
                        "start_timestamp": row["start_timestamp"],
                        "end_timestamp": row["end_timestamp"],
                        "listening_time_seconds": row["listening_time_seconds"],
                        "action_type": row["action_type"],
                        "created_at": row["created_at"]
                    }
                    for row in rows
                ]
        except sqlite3.Error as e:
            logger.error(f"Error getting listening history: {e}")
            return []
