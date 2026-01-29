#!/usr/bin/env python3
"""
Run against the most recent 100 test_runs in ~/.stream_checker/stream_checker.db.
Report: total rows, count with audio_analysis.status=="ok", count where
audio_quality.average_volume_db is missing/NULL/non-numeric, count where
silence_detection.silence_percentage is missing/NULL/non-numeric, and top 3 error strings by frequency.
"""

import json
import math
import sqlite3
import sys
from pathlib import Path
from collections import Counter

DB_PATH = Path.home() / ".stream_checker" / "stream_checker.db"


def is_numeric(val):
    if val is None:
        return False
    if isinstance(val, (int, float)):
        if isinstance(val, float) and math.isnan(val):
            return False
        return True
    return False


def main():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT test_run_id, stream_id, timestamp, phase, results
        FROM test_runs
        ORDER BY timestamp DESC
        LIMIT 100
    """)
    rows = cursor.fetchall()
    conn.close()

    total = len(rows)
    status_ok = 0
    avg_volume_missing_or_non_numeric = 0
    silence_pct_missing_or_non_numeric = 0
    error_strings = []

    for row in rows:
        try:
            results = json.loads(row["results"]) if row["results"] else {}
        except json.JSONDecodeError:
            results = {}
        audio = results.get("audio_analysis") or {}

        if audio.get("status") == "ok":
            status_ok += 1

        # audio_quality.average_volume_db missing/NULL/non-numeric
        aq = audio.get("audio_quality")
        if aq is None:
            avg_volume_missing_or_non_numeric += 1
        else:
            v = aq.get("average_volume_db")
            if not is_numeric(v):
                avg_volume_missing_or_non_numeric += 1

        # silence_detection.silence_percentage missing/NULL/non-numeric
        sd = audio.get("silence_detection")
        if sd is None:
            silence_pct_missing_or_non_numeric += 1
        else:
            v = sd.get("silence_percentage")
            if not is_numeric(v):
                silence_pct_missing_or_non_numeric += 1

        err = audio.get("error")
        if err and isinstance(err, str) and err.strip():
            error_strings.append(err.strip())

    error_counts = Counter(error_strings)
    top3_errors = error_counts.most_common(3)

    print("total_rows:", total)
    print("audio_analysis.status_ok:", status_ok)
    print("audio_quality.average_volume_db_missing_or_non_numeric:", avg_volume_missing_or_non_numeric)
    print("silence_detection.silence_percentage_missing_or_non_numeric:", silence_pct_missing_or_non_numeric)
    print("top_3_error_strings_by_frequency:")
    for err, count in top3_errors:
        print(f"  {count}: {err!r}")


if __name__ == "__main__":
    main()
