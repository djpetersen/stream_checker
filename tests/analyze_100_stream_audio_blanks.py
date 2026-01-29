#!/usr/bin/env python3
"""
Extract results from the most recent 100-stream test run from the SQLite DB,
identify every stream whose audio analysis results are blank/NULL/missing or "not tested".
Output: table (stream id/URL, blank fields, phase(s), timestamps, error text) and
blank-pattern counts for root-cause analysis.
"""

import sqlite3
import json
import sys
from pathlib import Path
from collections import defaultdict

# Project root
sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path.home() / ".stream_checker" / "stream_checker.db"

# Expected audio_analysis sub-structures when Phase 3 succeeded (all populated)
AUDIO_KEYS = ("silence_detection", "error_detection", "audio_quality", "error", "sample_duration_seconds")


def is_blank_or_not_tested(val):
    """True if value is considered blank or 'not tested'."""
    if val is None:
        return True
    if isinstance(val, str):
        return not val.strip() or val.strip().lower() in ("not tested", "n/a", "-")
    if isinstance(val, (list, dict)):
        return len(val) == 0
    return False


def subfield_blank(audio, key, subkey=None):
    """Check if a top-level or nested audio_analysis field is blank/missing."""
    if key not in audio:
        return True
    v = audio[key]
    if v is None:
        return True
    if subkey is not None:
        if not isinstance(v, dict) or subkey not in v:
            return True
        v = v[subkey]
    if isinstance(v, (list, dict)) and len(v) == 0:
        return False  # empty list/dict is a valid "no findings"
    return is_blank_or_not_tested(v)


def describe_blank_fields(audio):
    """Return list of strings describing which audio_analysis fields are blank."""
    blanks = []
    if not audio:
        return ["audio_analysis missing"]
    # Top-level error
    if audio.get("error"):
        blanks.append(f"error set: {str(audio['error'])[:80]}")
    # Sub-structures
    for key in ("silence_detection", "error_detection", "audio_quality"):
        if key not in audio or audio[key] is None:
            blanks.append(f"{key} missing")
        else:
            d = audio[key]
            if key == "silence_detection" and isinstance(d, dict):
                if d.get("silence_percentage") is None and "error" not in str(audio.get("error", "")):
                    blanks.append("silence_detection.silence_percentage blank")
            elif key == "audio_quality" and isinstance(d, dict):
                if d.get("average_volume_db") is None and d.get("peak_volume_db") is None and not audio.get("error"):
                    blanks.append("audio_quality (all None)")
    # Entire audio_analysis present but looks like default/error-only (no real analysis)
    if "error" in audio and audio["error"]:
        if not blanks:
            blanks.append("error only (no analysis)")
        # Ensure we list which sub-fields are still default
        for key in ("silence_detection", "error_detection", "audio_quality"):
            if key in audio and isinstance(audio[key], dict):
                pass  # already covered
            elif key not in audio or audio[key] is None:
                blanks.append(f"{key} missing")
    return blanks if blanks else ["none (all present)"]


def blank_pattern(results, phase):
    """Produce a canonical pattern key for aggregation (e.g. 'no_audio_section', 'error_only_silence_missing')."""
    audio = results.get("audio_analysis") if results else None
    if not audio:
        return "no_audio_analysis_section"
    err = audio.get("error") or ""
    err_lower = err.lower() if isinstance(err, str) else ""
    if "failed to download" in err_lower:
        return "error_failed_to_download_audio_sample"
    if "failed to load audio data" in err_lower:
        return "error_failed_to_load_audio_data"
    if err:
        return "error_other"
    blanks = describe_blank_fields(audio)
    if "none (all present)" in blanks:
        return "all_present"
    # Simplify to pattern
    parts = []
    if any("silence" in b for b in blanks):
        parts.append("silence_blank")
    if any("audio_quality" in b for b in blanks):
        parts.append("audio_quality_blank")
    if any("error_detection" in b for b in blanks):
        parts.append("error_detection_blank")
    if any("error only" in b for b in blanks):
        parts.append("error_only")
    return "_".join(parts) if parts else "other_blank"


def main():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Most recent 100 test runs (each row = one stream's latest phase in that "batch" concept;
    # we take 100 most recent rows; same stream can appear if run multiple times)
    cursor.execute("""
        SELECT tr.test_run_id, tr.stream_id, tr.timestamp, tr.phase, tr.results,
               s.url AS stream_url
        FROM test_runs tr
        LEFT JOIN streams s ON s.stream_id = tr.stream_id
        ORDER BY tr.timestamp DESC
        LIMIT 100
    """)
    rows = cursor.fetchall()
    conn.close()

    # Build table rows and pattern counts
    table_rows = []
    pattern_counts = defaultdict(int)

    for row in rows:
        try:
            results = json.loads(row["results"]) if row["results"] else {}
        except json.JSONDecodeError:
            results = {}
        phase = row["phase"]
        audio = results.get("audio_analysis")
        stream_id = row["stream_id"] or "N/A"
        url = row["stream_url"] or results.get("stream_url") or "N/A"
        if len(url) > 70:
            url_display = url[:67] + "..."
        else:
            url_display = url

        # Consider "blank" if: no audio_analysis at all, or phase < 3, or audio has error/blank sub-fields
        blank_fields = []
        if phase < 3:
            blank_fields.append("phase<3 (audio not run)")
        if not audio:
            blank_fields.append("audio_analysis missing")
        else:
            blank_fields.extend(describe_blank_fields(audio))

        # Only include rows where something is blank or "not tested"
        has_blank = (
            phase < 3
            or not audio
            or audio.get("error")
            or any(
                subfield_blank(audio, k)
                for k in ("silence_detection", "error_detection", "audio_quality")
                if audio
            )
        )
        # Normalize: treat "none (all present)" as no blank for inclusion
        if blank_fields and blank_fields != ["none (all present)"]:
            has_blank = True

        pattern = blank_pattern(results, phase)
        pattern_counts[pattern] += 1

        stored_error = ""
        if audio and audio.get("error"):
            stored_error = str(audio["error"])[:120]

        # Only include rows that have actual blanks (exclude "all_present")
        if pattern != "all_present":
            table_rows.append({
                "stream_id": stream_id,
                "url": url_display,
                "blank_fields": blank_fields,
                "phase": phase,
                "timestamp": row["timestamp"],
                "stored_error": stored_error,
                "pattern": pattern,
            })

    # Sort table by timestamp desc
    table_rows.sort(key=lambda x: x["timestamp"] or "", reverse=True)

    # ----- Output -----
    print("=" * 100)
    print("STREAMS WITH BLANK/MISSING/NOT-TESTED AUDIO ANALYSIS (most recent 100 test runs)")
    print("=" * 100)
    print(f"Total runs analyzed: 100. Rows with blanks: {len(table_rows)}.")
    print()
    print(f"{'Stream ID':<36} | {'URL':<72} | {'Blank fields':<40} | {'Phase':<6} | {'Timestamp':<24} | Stored error")
    print("-" * 100)
    if not table_rows:
        print("(No rows with blank/missing audio analysis in the most recent 100 runs)")
    for r in table_rows:
        bf = "; ".join(r["blank_fields"])[:38] if r["blank_fields"] else "-"
        err = (r["stored_error"] or "-")[:60]
        print(f"{r['stream_id']:<36} | {r['url']:<72} | {bf:<40} | {r['phase']:<6} | {str(r['timestamp']):<24} | {err}")
    print()
    print("=" * 100)
    print("BLANK PATTERN COUNTS (for root-cause analysis)")
    print("=" * 100)
    for pat, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        print(f"  {count:>4}  {pat}")
    print()
    # Top 5 patterns
    top5 = sorted(pattern_counts.items(), key=lambda x: -x[1])[:5]
    print("Top 5 patterns (for code-path tracing):")
    for i, (pat, count) in enumerate(top5, 1):
        print(f"  {i}. {pat} ({count})")


if __name__ == "__main__":
    main()
