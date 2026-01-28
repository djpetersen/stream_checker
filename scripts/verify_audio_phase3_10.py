#!/usr/bin/env python3
"""Minimal script to verify Phase 3 audio analysis on 10 streams"""

import sys
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Test stream URLs - edit this list as needed
TEST_STREAMS = [
    "http://streams.radiomast.io/ref-128k-mp3-stereo",
    "http://streams.radiomast.io/ref-96k-mp3-stereo",
    "http://streams.radiomast.io/ref-64k-mp3-stereo",
    "http://streams.radiomast.io/ref-32k-mp3-mono",
    "http://streams.radiomast.io/ref-128k-aaclc-stereo",
    "http://streams.radiomast.io/ref-64k-heaacv1-stereo",
    "http://icecast.omroep.nl/radio1-bb-mp3",
    "http://ice1.somafm.com/groovesalad-128-mp3",
    "http://ice1.somafm.com/dronezone-128-mp3",
    "https://icecast.radiofrance.fr/fip-hifi.mp3",
]

# Configuration
PER_STREAM_TIMEOUT = 90  # seconds
MIN_PASS_COUNT = 8  # require at least 8/10 to pass

# Setup paths
project_root = Path(__file__).parent.parent
stream_checker_script = project_root / "stream_checker.py"
output_dir = project_root / "scratch" / "audio_verify"
output_dir.mkdir(parents=True, exist_ok=True)


def classify_failure_type(audio_data: Dict[str, Any], stderr: str) -> str:
    """Classify failure type: 'download', 'load_raw', or 'timeout'"""
    error_msg = audio_data.get("error", "").lower()
    stderr_lower = stderr.lower()
    
    if "timeout" in error_msg or "timeout" in stderr_lower:
        return "timeout"
    elif "failed to download" in error_msg or "download" in error_msg:
        return "download"
    elif "failed to load" in error_msg or "load" in error_msg:
        return "load_raw"
    else:
        return "unknown"


def is_pass(audio_data: Dict[str, Any]) -> bool:
    """Check if audio analysis passed: no error, and numeric silence/volume fields"""
    # Check for error
    if "error" in audio_data and audio_data["error"]:
        return False
    
    # Check silence_detection.silence_percentage is numeric
    silence = audio_data.get("silence_detection", {})
    silence_pct = silence.get("silence_percentage")
    if silence_pct is None or not isinstance(silence_pct, (int, float)):
        return False
    
    # Check audio_quality.average_volume_db is numeric
    quality = audio_data.get("audio_quality", {})
    avg_volume = quality.get("average_volume_db")
    if avg_volume is None or not isinstance(avg_volume, (int, float)):
        return False
    
    return True


def test_stream(index: int, url: str) -> Dict[str, Any]:
    """Test a single stream and return result dict"""
    json_path = output_dir / f"{index}.json"
    log_path = output_dir / f"{index}.log"
    
    start_time = time.time()
    
    try:
        # Run stream_checker.py
        result = subprocess.run(
            [sys.executable, str(stream_checker_script), "--url", url, "--phase", "3", "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=PER_STREAM_TIMEOUT
        )
        
        elapsed = time.time() - start_time
        
        # Save stderr to log file
        with open(log_path, "w") as f:
            f.write(result.stderr)
        
        # Parse JSON
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {
                "url": url,
                "pass": False,
                "error": "Invalid JSON output",
                "elapsed": elapsed,
                "failure_type": "unknown"
            }
        
        # Save JSON
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)
        
        # Check audio_analysis section
        audio_data = data.get("audio_analysis", {})
        passed = is_pass(audio_data)
        
        error_str = audio_data.get("error", "") if not passed else ""
        failure_type = classify_failure_type(audio_data, result.stderr) if not passed else ""
        
        return {
            "url": url,
            "pass": passed,
            "error": error_str,
            "elapsed": elapsed,
            "failure_type": failure_type
        }
        
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        # Save empty log for timeout
        with open(log_path, "w") as f:
            f.write(f"Timeout after {PER_STREAM_TIMEOUT}s\n")
        # Save minimal JSON
        with open(json_path, "w") as f:
            json.dump({"error": "Timeout", "url": url}, f, indent=2)
        
        return {
            "url": url,
            "pass": False,
            "error": f"Timeout ({PER_STREAM_TIMEOUT}s)",
            "elapsed": elapsed,
            "failure_type": "timeout"
        }
    
    except Exception as e:
        elapsed = time.time() - start_time
        # Save error log
        with open(log_path, "w") as f:
            f.write(f"Exception: {e}\n")
        # Save minimal JSON
        with open(json_path, "w") as f:
            json.dump({"error": str(e), "url": url}, f, indent=2)
        
        return {
            "url": url,
            "pass": False,
            "error": str(e),
            "elapsed": elapsed,
            "failure_type": "unknown"
        }


def main():
    """Main execution"""
    print("=" * 80)
    print("Phase 3 Audio Analysis Verification - 10 Streams")
    print("=" * 80)
    print(f"Output directory: {output_dir}")
    print(f"Per-stream timeout: {PER_STREAM_TIMEOUT}s")
    print(f"Minimum pass count: {MIN_PASS_COUNT}/10")
    print()
    
    results = []
    
    # Test each stream
    for i, url in enumerate(TEST_STREAMS, 1):
        print(f"[{i}/{len(TEST_STREAMS)}] Testing: {url}")
        result = test_stream(i, url)
        results.append(result)
        
        status = "PASS" if result["pass"] else "FAIL"
        print(f"  {status} - {result['elapsed']:.1f}s - {result['error'] or 'OK'}")
    
    # Print summary table
    print()
    print("=" * 80)
    print("Summary Table")
    print("=" * 80)
    print(f"{'URL':<50} {'Status':<6} {'Error':<30} {'Time':<8} {'Type':<10}")
    print("-" * 80)
    
    for r in results:
        url_short = r["url"][:48] + ".." if len(r["url"]) > 50 else r["url"]
        status = "PASS" if r["pass"] else "FAIL"
        error_short = (r["error"][:28] + "..") if len(r["error"]) > 30 else r["error"]
        elapsed_str = f"{r['elapsed']:.1f}s"
        failure_type = r["failure_type"] if not r["pass"] else ""
        
        print(f"{url_short:<50} {status:<6} {error_short:<30} {elapsed_str:<8} {failure_type:<10}")
    
    # Count passes
    pass_count = sum(1 for r in results if r["pass"])
    print()
    print(f"Passed: {pass_count}/10")
    print(f"Failed: {10 - pass_count}/10")
    
    # Exit code
    if pass_count >= MIN_PASS_COUNT:
        print(f"\n✅ SUCCESS: {pass_count}/10 passed (>= {MIN_PASS_COUNT})")
        sys.exit(0)
    else:
        print(f"\n❌ FAILURE: Only {pass_count}/10 passed (need >= {MIN_PASS_COUNT})")
        sys.exit(1)


if __name__ == "__main__":
    main()
