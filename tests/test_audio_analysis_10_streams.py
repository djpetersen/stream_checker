#!/usr/bin/env python3
"""Test audio analysis on 10 streams and verify statistics are produced"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from stream_checker.core.audio_analysis import AudioAnalyzer

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
print("Audio Analysis Test - 10 Streams")
print("=" * 80)
print(f"Start time: {datetime.now()}")
print(f"Testing {len(TEST_STREAMS)} streams")
print()

analyzer = AudioAnalyzer(sample_duration=10, silence_threshold_db=-40.0)

results = []
success_count = 0
failed_count = 0

for i, url in enumerate(TEST_STREAMS, 1):
    print(f"[{i}/{len(TEST_STREAMS)}] Testing: {url}")
    print("-" * 80)
    
    try:
        result = analyzer.analyze(url)
        
        if "error" in result and result["error"]:
            print(f"❌ FAILED: {result['error']}")
            failed_count += 1
            results.append({
                "url": url,
                "status": "failed",
                "error": result["error"],
                "statistics": None
            })
        else:
            print("✅ SUCCESS - Audio analysis completed")
            success_count += 1
            
            # Extract and display statistics
            stats = {}
            
            # Silence detection statistics
            if "silence_detection" in result:
                silence = result["silence_detection"]
                stats["silence_detected"] = silence.get("silence_detected", False)
                stats["silence_percentage"] = silence.get("silence_percentage", 0.0)
                stats["silence_periods_count"] = len(silence.get("silence_periods", []))
                print(f"  Silence Detection:")
                print(f"    Detected: {stats['silence_detected']}")
                print(f"    Percentage: {stats['silence_percentage']:.2f}%")
                print(f"    Periods: {stats['silence_periods_count']}")
            
            # Audio quality statistics
            if "audio_quality" in result:
                quality = result["audio_quality"]
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
            if "error_detection" in result:
                error_det = result["error_detection"]
                stats["error_detected"] = error_det.get("error_detected", False)
                stats["error_messages_count"] = len(error_det.get("error_messages", []))
                stats["repetitive_pattern"] = error_det.get("repetitive_pattern_detected", False)
                print(f"  Error Detection:")
                print(f"    Errors Detected: {stats['error_detected']}")
                print(f"    Error Messages: {stats['error_messages_count']}")
                print(f"    Repetitive Pattern: {stats['repetitive_pattern']}")
            
            # Sample duration
            stats["sample_duration_seconds"] = result.get("sample_duration_seconds", 10)
            print(f"  Sample Duration: {stats['sample_duration_seconds']} seconds")
            
            results.append({
                "url": url,
                "status": "success",
                "error": None,
                "statistics": stats
            })
    
    except Exception as e:
        print(f"💥 EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
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
    
    # Average statistics across all successful runs
    avg_silence_pct = sum(r["statistics"]["silence_percentage"] for r in successful_results if r["statistics"] and "silence_percentage" in r["statistics"]) / len(successful_results)
    avg_volume_db = sum(r["statistics"]["average_volume_db"] for r in successful_results if r["statistics"] and r["statistics"].get("average_volume_db") is not None) / len([r for r in successful_results if r["statistics"] and r["statistics"].get("average_volume_db") is not None])
    avg_peak_db = sum(r["statistics"]["peak_volume_db"] for r in successful_results if r["statistics"] and r["statistics"].get("peak_volume_db") is not None) / len([r for r in successful_results if r["statistics"] and r["statistics"].get("peak_volume_db") is not None])
    
    print(f"Average Silence Percentage: {avg_silence_pct:.2f}%")
    if avg_volume_db:
        print(f"Average Volume: {avg_volume_db:.2f} dB")
    if avg_peak_db:
        print(f"Average Peak Volume: {avg_peak_db:.2f} dB")
    
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
elif success_count >= len(TEST_STREAMS) * 0.8:  # 80% success rate
    print(f"\n✅ Audio analysis working - {success_count}/{len(TEST_STREAMS)} streams succeeded")
    sys.exit(0)
else:
    print(f"\n⚠️  Partial success - {success_count}/{len(TEST_STREAMS)} streams succeeded")
    sys.exit(1)
