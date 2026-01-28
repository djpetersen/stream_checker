#!/usr/bin/env python3
"""
Analyze audio analysis errors in the last 100 test runs
"""

import sqlite3
import json
import sys
from pathlib import Path

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

# Analyze audio analysis errors
total_runs = 0
audio_analysis_present = 0
audio_analysis_error = 0
failed_to_load_count = 0
other_errors = []
no_audio_analysis = 0

for row in rows:
    total_runs += 1
    try:
        results = json.loads(row["results"]) if row["results"] else {}
    except json.JSONDecodeError:
        continue
    
    if "audio_analysis" in results:
        audio_analysis_present += 1
        audio = results["audio_analysis"]
        
        if "error" in audio and audio["error"]:
            audio_analysis_error += 1
            error_msg = str(audio["error"]).lower()
            
            if "failed to load" in error_msg or "failed to load audio data" in error_msg:
                failed_to_load_count += 1
            else:
                other_errors.append({
                    "test_run_id": row["test_run_id"],
                    "timestamp": row["timestamp"],
                    "error": audio["error"]
                })
    else:
        no_audio_analysis += 1

# Print analysis
print("=" * 60)
print("Audio Analysis Error Analysis")
print("=" * 60)
print(f"Total test runs analyzed: {total_runs}")
print(f"Runs with audio_analysis section: {audio_analysis_present}")
print(f"Runs with audio_analysis.error: {audio_analysis_error}")
print(f"Runs with 'failed to load audio data' error: {failed_to_load_count}")
print(f"Runs with other audio errors: {len(other_errors)}")
print(f"Runs without audio_analysis section: {no_audio_analysis}")
print()

if failed_to_load_count > 0:
    percentage = (failed_to_load_count / audio_analysis_present * 100) if audio_analysis_present > 0 else 0
    print(f"⚠️  {failed_to_load_count} out of {audio_analysis_present} audio analysis runs ({percentage:.1f}%) have 'failed to load audio data' error")
    print()

if other_errors:
    print("Other audio analysis errors found:")
    for err in other_errors[:10]:  # Show first 10
        print(f"  - {err['timestamp']}: {err['error'][:100]}")
    if len(other_errors) > 10:
        print(f"  ... and {len(other_errors) - 10} more")
    print()

# Show sample of failed runs
if failed_to_load_count > 0:
    print("Sample of failed runs:")
    count = 0
    for row in rows:
        if count >= 5:
            break
        try:
            results = json.loads(row["results"]) if row["results"] else {}
            if "audio_analysis" in results:
                audio = results["audio_analysis"]
                if "error" in audio and audio["error"]:
                    error_msg = str(audio["error"]).lower()
                    if "failed to load" in error_msg:
                        print(f"  Test Run ID: {row['test_run_id']}")
                        print(f"  Timestamp: {row['timestamp']}")
                        print(f"  Phase: {row['phase']}")
                        print(f"  Error: {audio['error']}")
                        if "connectivity" in results:
                            connectivity = results["connectivity"]
                            print(f"  Stream URL: {results.get('stream_url', 'N/A')}")
                            print(f"  HTTP Status: {connectivity.get('http_status', 'N/A')}")
                            print(f"  Content Type: {connectivity.get('content_type', 'N/A')}")
                        print()
                        count += 1
        except:
            continue

conn.close()
