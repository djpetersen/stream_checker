#!/usr/bin/env python3
"""
Diagnostic script to test audio loading with detailed logging
"""

import sys
import os
import logging
from pathlib import Path
import tempfile
import shutil
import platform

# CRITICAL: Set multiprocessing start method to 'spawn' on macOS BEFORE any other imports
if platform.system() == "Darwin":
    import multiprocessing
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from stream_checker.core.audio_analysis import AudioAnalyzer
from stream_checker.utils.config import Config
from stream_checker.utils.logging import setup_logging

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("stream_checker")
logger.setLevel(logging.DEBUG)

# Test URL from the analysis (one that's failing)
TEST_URL = "http://streams.radiomast.io/ref-128k-mp3-stereo"

print("=" * 70)
print("Audio Loading Diagnostic Test")
print("=" * 70)
print(f"Test URL: {TEST_URL}")
print()

# Create analyzer
analyzer = AudioAnalyzer(sample_duration=10, silence_threshold_db=-40.0)

print("Step 1: Testing _download_audio_sample")
print("-" * 70)
try:
    audio_file = analyzer._download_audio_sample(TEST_URL)
    if audio_file:
        print(f"✅ Download successful: {audio_file}")
        if os.path.exists(audio_file):
            file_size = os.path.getsize(audio_file)
            print(f"   File size: {file_size} bytes")
            print(f"   File exists: {os.path.exists(audio_file)}")
            print(f"   File readable: {os.access(audio_file, os.R_OK)}")
            
            # Check file type
            import subprocess
            try:
                file_result = subprocess.run(
                    ["/usr/bin/file", audio_file],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                print(f"   File type: {file_result.stdout.strip()}")
            except Exception as e:
                print(f"   Could not check file type: {e}")
        else:
            print(f"❌ File does not exist: {audio_file}")
    else:
        print("❌ Download failed: _download_audio_sample returned None")
except Exception as e:
    print(f"❌ Download exception: {e}")
    import traceback
    traceback.print_exc()
    audio_file = None

print()
print("Step 2: Testing _load_audio_raw")
print("-" * 70)
if audio_file and os.path.exists(audio_file):
    try:
        audio_data, sample_rate, channels = analyzer._load_audio_raw(audio_file)
        if audio_data is not None:
            print(f"✅ Load successful")
            print(f"   Sample rate: {sample_rate} Hz")
            print(f"   Channels: {channels}")
            print(f"   Audio data shape: {audio_data.shape}")
            print(f"   Audio data type: {audio_data.dtype}")
            print(f"   Audio data min: {audio_data.min()}")
            print(f"   Audio data max: {audio_data.max()}")
            print(f"   Audio data mean: {audio_data.mean():.2f}")
        else:
            print("❌ Load failed: _load_audio_raw returned None")
            print("   This is the source of 'Failed to load audio data' error")
    except Exception as e:
        print(f"❌ Load exception: {e}")
        import traceback
        traceback.print_exc()
else:
    print("⚠️  Skipping _load_audio_raw test (no audio file)")

print()
print("Step 3: Testing full analyze() method")
print("-" * 70)
try:
    result = analyzer.analyze(TEST_URL)
    print(f"Result keys: {list(result.keys())}")
    if "error" in result:
        print(f"❌ Error in result: {result['error']}")
    else:
        print("✅ No error in result")
        if "silence_detection" in result:
            silence = result["silence_detection"]
            print(f"   Silence detected: {silence.get('silence_detected', False)}")
            print(f"   Silence percentage: {silence.get('silence_percentage', 0)}%")
        if "audio_quality" in result:
            quality = result["audio_quality"]
            print(f"   Average volume: {quality.get('average_volume_db', 'N/A')} dB")
            print(f"   Peak volume: {quality.get('peak_volume_db', 'N/A')} dB")
except Exception as e:
    print(f"❌ Analyze exception: {e}")
    import traceback
    traceback.print_exc()

print()
print("Step 4: Checking ffmpeg availability")
print("-" * 70)
try:
    ffmpeg_path = analyzer._find_ffmpeg()
    if ffmpeg_path:
        print(f"✅ ffmpeg found: {ffmpeg_path}")
        # Test ffmpeg version
        import subprocess
        try:
            version_result = subprocess.run(
                [ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if version_result.returncode == 0:
                first_line = version_result.stdout.split('\n')[0]
                print(f"   Version: {first_line}")
            else:
                print(f"   ⚠️  ffmpeg version check failed: returncode={version_result.returncode}")
        except Exception as e:
            print(f"   ⚠️  Could not check ffmpeg version: {e}")
    else:
        print("❌ ffmpeg not found")
except Exception as e:
    print(f"❌ Exception checking ffmpeg: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 70)
print("Diagnostic complete")
print("=" * 70)
