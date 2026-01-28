#!/usr/bin/env python3
"""Get the last 10 streams where audio analysis failed"""

import sqlite3
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Get database path
try:
    from stream_checker.utils.config import Config
    config = Config()
    db_path = Path(config.get_path("database.path")).expanduser()
except Exception as e:
    db_path = Path.home() / ".stream_checker" / "stream_checker.db"

if not db_path.exists():
    print(f"ERROR: Database not found at {db_path}")
    sys.exit(1)

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get last 100 test runs
cursor.execute("""
    SELECT 
        test_run_id,
        stream_id,
        timestamp,
        phase,
        results
    FROM test_runs
    ORDER BY timestamp DESC
    LIMIT 100
""")

rows = cursor.fetchall()
failed_streams = []

for row in rows:
    try:
        results = json.loads(row["results"]) if row["results"] else {}
        if "audio_analysis" in results:
            audio = results["audio_analysis"]
            if "error" in audio and audio["error"]:
                stream_url = results.get("stream_url", "unknown")
                if stream_url != "unknown" and stream_url not in [s["url"] for s in failed_streams]:
                    failed_streams.append({
                        "url": stream_url,
                        "error": audio["error"],
                        "timestamp": row["timestamp"],
                        "test_run_id": row["test_run_id"]
                    })
                    if len(failed_streams) >= 10:
                        break
    except:
        continue

conn.close()

print("Last 10 streams with audio analysis failures:")
print("=" * 80)
for i, stream in enumerate(failed_streams, 1):
    print(f"{i}. {stream['url']}")
    print(f"   Error: {stream['error']}")
    print(f"   Timestamp: {stream['timestamp']}")
    print()

# Output URLs for testing
print("\nURLs for testing:")
for stream in failed_streams:
    print(stream['url'])
