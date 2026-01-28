#!/usr/bin/env python3
"""Debug a single stream download"""

import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from stream_checker.core.audio_analysis import AudioAnalyzer

# Test with a known good stream
test_url = "http://streams.radiomast.io/ref-128k-mp3-stereo"

print(f"Testing: {test_url}")
print("=" * 80)

analyzer = AudioAnalyzer(sample_duration=10, silence_threshold_db=-40.0)

# Test download directly
print("\nTesting _download_audio_sample directly...")
audio_file = analyzer._download_audio_sample(test_url)

if audio_file:
    print(f"✅ Download successful: {audio_file}")
    import os
    if os.path.exists(audio_file):
        print(f"   File exists: {os.path.exists(audio_file)}")
        print(f"   File size: {os.path.getsize(audio_file)} bytes")
    else:
        print(f"❌ File does not exist: {audio_file}")
else:
    print("❌ Download failed: returned None")

print("\nTesting full analyze() method...")
result = analyzer.analyze(test_url)

print(f"\nResult keys: {list(result.keys())}")
if "error" in result:
    print(f"❌ Error: {result['error']}")
else:
    print("✅ No error in result")
    if "silence_detection" in result:
        print(f"   Silence detected: {result['silence_detection'].get('silence_detected', False)}")
