#!/usr/bin/env python3
"""
Detailed analysis of audio download failures in the last 100 test runs
"""

import sqlite3
import json
import sys
from pathlib import Path
from collections import defaultdict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Get database path from config
try:
    from stream_checker.utils.config import Config
    config = Config()
    db_path = Path(config.get_path("database.path")).expanduser()
except Exception as e:
    print(f"Error loading config: {e}")
    # Default path
    db_path = Path.home() / ".stream_checker" / "stream_checker.db"

print(f"Database path: {db_path}")
print()

if not db_path.exists():
    print(f"ERROR: Database not found at {db_path}")
    sys.exit(1)

# Connect to database
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
print(f"Found {len(rows)} test runs in database")
print()

# Analyze download failures
total_runs = 0
download_failures = 0
load_failures = 0
other_errors = []
error_patterns = defaultdict(int)
stream_urls_failed = defaultdict(int)

for row in rows:
    total_runs += 1
    try:
        results = json.loads(row["results"]) if row["results"] else {}
    except json.JSONDecodeError:
        continue
    
    if "audio_analysis" in results:
        audio = results["audio_analysis"]
        
        if "error" in audio and audio["error"]:
            error_msg = str(audio["error"])
            error_lower = error_msg.lower()
            
            if "failed to download" in error_lower:
                download_failures += 1
                stream_url = results.get("stream_url", "unknown")
                stream_urls_failed[stream_url] += 1
                
                # Check connectivity info
                connectivity = results.get("connectivity", {})
                http_status = connectivity.get("http_status")
                content_type = connectivity.get("content_type")
                
                error_patterns[f"Download failed - HTTP {http_status}, Content-Type: {content_type}"] += 1
                
            elif "failed to load" in error_lower:
                load_failures += 1
            else:
                other_errors.append({
                    "test_run_id": row["test_run_id"],
                    "timestamp": row["timestamp"],
                    "error": error_msg,
                    "stream_url": results.get("stream_url", "unknown")
                })

# Print analysis
print("=" * 80)
print("Audio Download Failure Analysis")
print("=" * 80)
print(f"Total test runs analyzed: {total_runs}")
print(f"Download failures: {download_failures} ({download_failures*100/total_runs:.1f}%)")
print(f"Load failures: {load_failures} ({load_failures*100/total_runs:.1f}%)")
print(f"Other errors: {len(other_errors)}")
print()

if download_failures > 0:
    print("=" * 80)
    print("Download Failure Patterns")
    print("=" * 80)
    for pattern, count in sorted(error_patterns.items(), key=lambda x: x[1], reverse=True):
        print(f"  {pattern}: {count}")
    print()
    
    print("=" * 80)
    print("Streams with Most Download Failures")
    print("=" * 80)
    for url, count in sorted(stream_urls_failed.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {url}: {count} failures")
    print()

# Show sample failures with connectivity info
if download_failures > 0:
    print("=" * 80)
    print("Sample Download Failures (with connectivity info)")
    print("=" * 80)
    count = 0
    for row in rows:
        if count >= 10:
            break
        try:
            results = json.loads(row["results"]) if row["results"] else {}
            if "audio_analysis" in results:
                audio = results["audio_analysis"]
                if "error" in audio and audio["error"]:
                    error_msg = str(audio["error"]).lower()
                    if "failed to download" in error_msg:
                        connectivity = results.get("connectivity", {})
                        print(f"\n  Test Run ID: {row['test_run_id']}")
                        print(f"  Timestamp: {row['timestamp']}")
                        print(f"  Stream URL: {results.get('stream_url', 'N/A')}")
                        print(f"  HTTP Status: {connectivity.get('http_status', 'N/A')}")
                        print(f"  Content Type: {connectivity.get('content_type', 'N/A')}")
                        print(f"  Error: {audio['error']}")
                        count += 1
        except:
            continue
    print()

conn.close()
