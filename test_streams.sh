#!/bin/bash
# Test script for 10 audio streams

STREAMS=(
    "http://streams.radiomast.io/ref-128k-mp3-stereo"
    "http://streams.radiomast.io/ref-32k-mp3-mono"
    "http://streams.radiomast.io/ref-128k-aaclc-stereo"
    "http://streams.radiomast.io/ref-64k-heaacv1-stereo"
    "http://icecast.omroep.nl/radio1-bb-mp3"
    "http://icecast.omroep.nl/radio2-bb-mp3"
    "http://streams.radiomast.io/ref-64k-ogg-vorbis-stereo"
    "http://streams.radiomast.io/ref-64k-ogg-opus-stereo"
    "http://ice1.somafm.com/groovesalad-128-mp3"
    "http://ice1.somafm.com/dronezone-128-mp3"
)

PASSED=0
FAILED=0
FAILED_STREAMS=()

echo "Testing ${#STREAMS[@]} audio streams..."
echo "=========================================="
echo ""

for i in "${!STREAMS[@]}"; do
    URL="${STREAMS[$i]}"
    NUM=$((i + 1))
    
    echo "[$NUM/${#STREAMS[@]}] Testing: $URL"
    echo "----------------------------------------"
    
    # Run with phase 1 only for faster testing (connectivity check)
    if python3 stream_checker.py --url "$URL" --phase 1 --output-format json > /tmp/stream_test_${NUM}.json 2>&1; then
        echo "✅ PASSED"
        ((PASSED++))
    else
        echo "❌ FAILED"
        ((FAILED++))
        FAILED_STREAMS+=("$URL")
        echo "Error output:"
        tail -20 /tmp/stream_test_${NUM}.json
    fi
    echo ""
done

echo "=========================================="
echo "Summary:"
echo "  Passed: $PASSED"
echo "  Failed: $FAILED"
echo ""

if [ $FAILED -gt 0 ]; then
    echo "Failed streams:"
    for stream in "${FAILED_STREAMS[@]}"; do
        echo "  - $stream"
    done
    exit 1
else
    echo "All streams passed! ✅"
    exit 0
fi
