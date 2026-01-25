"""Database models and schema"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

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
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn
    
    def add_stream(self, stream_id: str, url: str, name: Optional[str] = None):
        """Add or update stream"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO streams (stream_id, url, name, last_tested)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (stream_id, url, name))
            
            conn.commit()
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def update_stream_test_count(self, stream_id: str):
        """Increment test count for stream"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE streams 
                SET test_count = test_count + 1,
                    last_tested = CURRENT_TIMESTAMP
                WHERE stream_id = ?
            """, (stream_id,))
            
            conn.commit()
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def add_test_run(
        self,
        test_run_id: str,
        stream_id: str,
        phase: int,
        results: Dict[str, Any]
    ):
        """Add or update test run result"""
        conn = None
        try:
            conn = self.get_connection()
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
                    """, (phase, json.dumps(results), test_run_id))
                else:
                    # Update results but keep the higher phase number and update timestamp
                    cursor.execute("""
                        UPDATE test_runs 
                        SET results = ?, timestamp = CURRENT_TIMESTAMP
                        WHERE test_run_id = ?
                    """, (json.dumps(results), test_run_id))
            else:
                # Insert new record
                cursor.execute("""
                    INSERT INTO test_runs (test_run_id, stream_id, phase, results)
                    VALUES (?, ?, ?, ?)
                """, (test_run_id, stream_id, phase, json.dumps(results)))
            
            conn.commit()
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def get_stream_history(self, stream_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get test run history for a stream"""
        conn = None
        try:
            conn = self.get_connection()
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
        finally:
            if conn:
                conn.close()
    
    def get_stream_info(self, stream_id: str) -> Optional[Dict[str, Any]]:
        """Get stream information"""
        conn = None
        try:
            conn = self.get_connection()
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
        finally:
            if conn:
                conn.close()
