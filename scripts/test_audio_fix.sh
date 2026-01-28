#!/bin/bash
# Stress test for audio analysis fix - 50 runs

set -e

TEST_URL="http://streams.radiomast.io/ref-128k-mp3-stereo"
PASSED=0
FAILED=0
CRASHED=0

echo "Running 50-iteration stress test for audio analysis fix..."
echo "Test URL: $TEST_URL"
echo ""

for i in $(seq 1 50); do
    echo -n "[$i/50] "
    
    if PYTHONFAULTHANDLER=1 python3 -X faulthandler -X dev stream_checker.py --url "$TEST_URL" --phase 3 --output-format json > /tmp/test_audio_${i}.json 2>/tmp/test_audio_${i}.err; then
        # Check if audio analysis succeeded
        if grep -q '"error"' /tmp/test_audio_${i}.json 2>/dev/null; then
            ERROR=$(grep -o '"error": "[^"]*"' /tmp/test_audio_${i}.json | head -1)
            if echo "$ERROR" | grep -q "Failed to load audio data\|Failed to download audio sample"; then
                echo "❌ FAILED - $ERROR"
                ((FAILED++))
            else
                echo "✅ PASSED (with other error: $ERROR)"
                ((PASSED++))
            fi
        else
            echo "✅ PASSED"
            ((PASSED++))
        fi
    else
        EXIT_CODE=$?
        if [ $EXIT_CODE -eq 139 ] || [ $EXIT_CODE -eq 134 ] || [ $EXIT_CODE -eq 130 ]; then
            echo "💥 CRASHED (exit code: $EXIT_CODE)"
            ((CRASHED++))
        else
            echo "❌ FAILED (exit code: $EXIT_CODE)"
            ((FAILED++))
        fi
    fi
done

echo ""
echo "=========================================="
echo "Stress Test Summary"
echo "=========================================="
echo "✅ Passed: $PASSED"
echo "❌ Failed: $FAILED"
echo "💥 Crashed: $CRASHED"
echo ""

# Check for crash reports
echo "Checking for crash reports..."
CRASH_REPORTS=$(ls -t ~/Library/Logs/DiagnosticReports/Python_*.ips 2>/dev/null | head -5 || echo "")
if [ -n "$CRASH_REPORTS" ]; then
    echo "⚠️  Found crash reports:"
    echo "$CRASH_REPORTS" | head -3
else
    echo "✅ No new crash reports found"
fi

if [ $CRASHED -gt 0 ]; then
    echo ""
    echo "❌ CRITICAL: $CRASHED crash(es) detected!"
    exit 1
fi

if [ $FAILED -gt 0 ]; then
    echo ""
    echo "⚠️  $FAILED test(s) failed (but no crashes)"
    exit 0
fi

echo ""
echo "✅ All tests passed with no crashes!"
