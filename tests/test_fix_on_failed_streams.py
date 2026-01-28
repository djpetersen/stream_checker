#!/usr/bin/env python3
"""Test the audio download fix on the last 10 failed streams"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from stream_checker.core.audio_analysis import AudioAnalyzer

# Get failed streams
import subprocess
result = subprocess.run(
    [sys.executable, str(Path(__file__).parent / "get_failed_streams.py")],
    capture_output=True,
    text=True
)

# Extract URLs
urls = []
for line in result.stdout.split('\n'):
    if line.startswith('http'):
        urls.append(line.strip())

print("=" * 80)
print("Testing Audio Download Fix on Previously Failed Streams")
print("=" * 80)
print(f"Testing {len(urls)} streams that previously failed")
print()

analyzer = AudioAnalyzer(sample_duration=10, silence_threshold_db=-40.0)

results = []
for i, url in enumerate(urls[:10], 1):
    print(f"[{i}/{len(urls[:10])}] Testing: {url}")
    print("-" * 80)
    
    try:
        result = analyzer.analyze(url)
        
        if "error" in result and result["error"]:
            status = "❌ FAILED"
            error_msg = result["error"]
            results.append({
                "url": url,
                "status": "failed",
                "error": error_msg
            })
        else:
            status = "✅ SUCCESS"
            results.append({
                "url": url,
                "status": "success",
                "error": None
            })
        
        print(f"Status: {status}")
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            print("Audio analysis completed successfully")
            if "silence_detection" in result:
                silence = result["silence_detection"]
                print(f"  Silence detected: {silence.get('silence_detected', False)}")
                print(f"  Silence percentage: {silence.get('silence_percentage', 0)}%")
            if "audio_quality" in result:
                quality = result["audio_quality"]
                print(f"  Average volume: {quality.get('average_volume_db', 'N/A')} dB")
        
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        results.append({
            "url": url,
            "status": "exception",
            "error": str(e)
        })
    
    print()

# Summary
print("=" * 80)
print("Summary")
print("=" * 80)
success_count = sum(1 for r in results if r["status"] == "success")
failed_count = sum(1 for r in results if r["status"] == "failed")
exception_count = sum(1 for r in results if r["status"] == "exception")

print(f"Total tested: {len(results)}")
print(f"✅ Success: {success_count} ({success_count*100/len(results):.1f}%)")
print(f"❌ Failed: {failed_count} ({failed_count*100/len(results):.1f}%)")
print(f"💥 Exception: {exception_count} ({exception_count*100/len(results):.1f}%)")
print()

if failed_count > 0:
    print("Failed streams:")
    for r in results:
        if r["status"] == "failed":
            print(f"  ❌ {r['url']}: {r['error']}")
    print()

if exception_count > 0:
    print("Exception streams:")
    for r in results:
        if r["status"] == "exception":
            print(f"  💥 {r['url']}: {r['error']}")
    print()

# Final verdict
if success_count == len(results):
    print("🎉 ALL TESTS PASSED - Fix is working!")
    sys.exit(0)
elif success_count > len(results) * 0.7:  # 70% success rate
    print(f"✅ Fix is working - {success_count}/{len(results)} streams now succeed (was 0/{len(results)})")
    sys.exit(0)
else:
    print(f"⚠️  Partial success - {success_count}/{len(results)} streams succeed")
    sys.exit(1)
