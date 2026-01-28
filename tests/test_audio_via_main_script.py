#!/usr/bin/env python3
"""Test audio analysis on 10 streams using the main stream_checker.py script"""

import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Test streams - mix of formats and sources
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

print("=" * 80)
print("Audio Analysis Test - 10 Streams (via stream_checker.py)")
print("=" * 80)
print(f"Start time: {datetime.now()}")
print(f"Testing {len(TEST_STREAMS)} streams")
print()

project_root = Path(__file__).parent.parent
stream_checker_script = project_root / "stream_checker.py"

results = []
success_count = 0
failed_count = 0

for i, url in enumerate(TEST_STREAMS, 1):
    print(f"[{i}/{len(TEST_STREAMS)}] Testing: {url}")
    print("-" * 80)
    
    try:
        # Run stream_checker.py with Phase 3 only
        result = subprocess.run(
            [sys.executable, str(stream_checker_script), "--url", url, "--phase", "3", "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout per stream
        )
        
        if result.returncode != 0:
            print(f"❌ FAILED: Process exited with code {result.returncode}")
            if result.stderr:
                print(f"   Error: {result.stderr[:200]}")
            failed_count += 1
            results.append({
                "url": url,
                "status": "failed",
                "error": f"Exit code {result.returncode}",
                "statistics": None
            })
            print()
            continue
        
        # Parse JSON output
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            print(f"❌ FAILED: Invalid JSON output")
            print(f"   Output: {result.stdout[:200]}")
            failed_count += 1
            results.append({
                "url": url,
                "status": "failed",
                "error": "Invalid JSON",
                "statistics": None
            })
            print()
            continue
        
        # Check for audio analysis results
        if "audio_analysis" not in data:
            print(f"❌ FAILED: No audio_analysis section in output")
            failed_count += 1
            results.append({
                "url": url,
                "status": "failed",
                "error": "No audio_analysis section",
                "statistics": None
            })
            print()
            continue
        
        audio = data["audio_analysis"]
        
        if "error" in audio and audio["error"]:
            print(f"❌ FAILED: {audio['error']}")
            failed_count += 1
            results.append({
                "url": url,
                "status": "failed",
                "error": audio["error"],
                "statistics": None
            })
        else:
            print("✅ SUCCESS - Audio analysis completed")
            success_count += 1
            
            # Extract and display statistics
            stats = {}
            
            # Silence detection statistics
            if "silence_detection" in audio:
                silence = audio["silence_detection"]
                stats["silence_detected"] = silence.get("silence_detected", False)
                stats["silence_percentage"] = silence.get("silence_percentage", 0.0)
                stats["silence_periods_count"] = len(silence.get("silence_periods", []))
                print(f"  Silence Detection:")
                print(f"    Detected: {stats['silence_detected']}")
                print(f"    Percentage: {stats['silence_percentage']:.2f}%")
                print(f"    Periods: {stats['silence_periods_count']}")
            
            # Audio quality statistics
            if "audio_quality" in audio:
                quality = audio["audio_quality"]
                stats["average_volume_db"] = quality.get("average_volume_db")
                stats["peak_volume_db"] = quality.get("peak_volume_db")
                stats["dynamic_range_db"] = quality.get("dynamic_range_db")
                stats["clipping_detected"] = quality.get("clipping_detected", False)
                print(f"  Audio Quality:")
                if stats["average_volume_db"] is not None:
                    print(f"    Average Volume: {stats['average_volume_db']:.2f} dB")
                if stats["peak_volume_db"] is not None:
                    print(f"    Peak Volume: {stats['peak_volume_db']:.2f} dB")
                if stats["dynamic_range_db"] is not None:
                    print(f"    Dynamic Range: {stats['dynamic_range_db']:.2f} dB")
                print(f"    Clipping Detected: {stats['clipping_detected']}")
            
            # Error detection statistics
            if "error_detection" in audio:
                error_det = audio["error_detection"]
                stats["error_detected"] = error_det.get("error_detected", False)
                stats["error_messages_count"] = len(error_det.get("error_messages", []))
                stats["repetitive_pattern"] = error_det.get("repetitive_pattern_detected", False)
                print(f"  Error Detection:")
                print(f"    Errors Detected: {stats['error_detected']}")
                print(f"    Error Messages: {stats['error_messages_count']}")
                print(f"    Repetitive Pattern: {stats['repetitive_pattern']}")
            
            # Sample duration
            stats["sample_duration_seconds"] = audio.get("sample_duration_seconds", 10)
            print(f"  Sample Duration: {stats['sample_duration_seconds']} seconds")
            
            results.append({
                "url": url,
                "status": "success",
                "error": None,
                "statistics": stats
            })
    
    except subprocess.TimeoutExpired:
        print(f"⏱️  TIMEOUT: Stream test exceeded 2 minute timeout")
        failed_count += 1
        results.append({
            "url": url,
            "status": "timeout",
            "error": "Timeout",
            "statistics": None
        })
    except Exception as e:
        print(f"💥 EXCEPTION: {e}")
        failed_count += 1
        results.append({
            "url": url,
            "status": "exception",
            "error": str(e),
            "statistics": None
        })
    
    print()

# Summary
print("=" * 80)
print("Test Summary")
print("=" * 80)
print(f"Total streams tested: {len(TEST_STREAMS)}")
print(f"✅ Success: {success_count} ({success_count*100/len(TEST_STREAMS):.1f}%)")
print(f"❌ Failed: {failed_count} ({failed_count*100/len(TEST_STREAMS):.1f}%)")
print()

# Statistics summary
successful_results = [r for r in results if r["status"] == "success"]
if successful_results:
    print("=" * 80)
    print("Statistics Summary (Successful Analyses)")
    print("=" * 80)
    
    # Calculate averages
    silence_values = [r["statistics"]["silence_percentage"] for r in successful_results if r["statistics"] and "silence_percentage" in r["statistics"]]
    volume_values = [r["statistics"]["average_volume_db"] for r in successful_results if r["statistics"] and r["statistics"].get("average_volume_db") is not None]
    peak_values = [r["statistics"]["peak_volume_db"] for r in successful_results if r["statistics"] and r["statistics"].get("peak_volume_db") is not None]
    
    if silence_values:
        avg_silence = sum(silence_values) / len(silence_values)
        print(f"Average Silence Percentage: {avg_silence:.2f}%")
    if volume_values:
        avg_volume = sum(volume_values) / len(volume_values)
        print(f"Average Volume: {avg_volume:.2f} dB")
    if peak_values:
        avg_peak = sum(peak_values) / len(peak_values)
        print(f"Average Peak Volume: {avg_peak:.2f} dB")
    
    print()
    print("Per-Stream Statistics:")
    for r in successful_results:
        if r["statistics"]:
            print(f"\n  {r['url']}")
            if "silence_percentage" in r["statistics"]:
                print(f"    Silence: {r['statistics']['silence_percentage']:.2f}%")
            if r["statistics"].get("average_volume_db") is not None:
                print(f"    Avg Volume: {r['statistics']['average_volume_db']:.2f} dB")
            if r["statistics"].get("peak_volume_db") is not None:
                print(f"    Peak Volume: {r['statistics']['peak_volume_db']:.2f} dB")
            if r["statistics"].get("dynamic_range_db") is not None:
                print(f"    Dynamic Range: {r['statistics']['dynamic_range_db']:.2f} dB")
            print(f"    Clipping: {r['statistics'].get('clipping_detected', False)}")

if failed_count > 0:
    print()
    print("=" * 80)
    print("Failed Streams")
    print("=" * 80)
    for r in results:
        if r["status"] != "success":
            print(f"  ❌ {r['url']}: {r['error']}")

print()
print("=" * 80)
print(f"End time: {datetime.now()}")
print("=" * 80)

# Final verdict
if success_count == len(TEST_STREAMS):
    print("\n🎉 ALL TESTS PASSED - Audio analysis working correctly!")
    sys.exit(0)
elif success_count >= len(TEST_STREAMS) * 0.7:  # 70% success rate
    print(f"\n✅ Audio analysis working - {success_count}/{len(TEST_STREAMS)} streams succeeded with statistics")
    sys.exit(0)
else:
    print(f"\n⚠️  Partial success - {success_count}/{len(TEST_STREAMS)} streams succeeded")
    sys.exit(1)
