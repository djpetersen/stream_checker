#!/bin/bash
# Stress test for Phase 3 audio analysis - 50 iterations
# Captures timing, ffmpeg argv, and failure details

set -e

TEST_URL="http://streams.radiomast.io/ref-128k-mp3-stereo"
RUNS=50
PASSED=0
FAILED=0
TIMEOUTS=0
CRASHES=0

echo "Phase 3 Audio Analysis Stress Test"
echo "=================================="
echo "Test URL: $TEST_URL"
echo "Iterations: $RUNS"
echo ""

START_TIME=$(date +%s)

for i in $(seq 1 $RUNS); do
    echo -n "[$i/$RUNS] "
    RUN_START=$(date +%s)
    
    # Run Phase 3 only
    if PYTHONFAULTHANDLER=1 python3 -X faulthandler -X dev stream_checker.py --url "$TEST_URL" --phase 3 --output-format json > /tmp/audio_test_${i}.json 2>/tmp/audio_test_${i}.err; then
        RUN_END=$(date +%s)
        ELAPSED=$((RUN_END - RUN_START))
        
        # Check if audio analysis succeeded
        if python3 -c "
import sys, json
try:
    with open('/tmp/audio_test_${i}.json', 'r') as f:
        data = json.load(f)
    audio = data.get('audio_analysis', {})
    error = audio.get('error')
    if error:
        print(f'FAILED: {error}')
        sys.exit(1)
    else:
        print(f'PASSED ({ELAPSED}s)')
        sys.exit(0)
except Exception as e:
    print(f'ERROR parsing JSON: {e}')
    sys.exit(1)
" 2>/dev/null; then
            echo "✅ PASSED (${ELAPSED}s)"
            ((PASSED++))
        else
            echo "❌ FAILED (${ELAPSED}s)"
            ((FAILED++))
            
            # Show error details
            if [ -f /tmp/audio_test_${i}.json ]; then
                ERROR=$(python3 -c "import sys, json; f=open('/tmp/audio_test_${i}.json'); d=json.load(f); print(d.get('audio_analysis',{}).get('error','Unknown'))" 2>/dev/null || echo "Unknown")
                echo "  Error: $ERROR"
            fi
            
            # Show first failure details
            if [ $FAILED -eq 1 ]; then
                echo ""
                echo "=== First Failure Details ==="
                echo "Elapsed time: ${ELAPSED}s"
                if [ -f /tmp/audio_test_${i}.err ]; then
                    echo "Stderr (last 20 lines):"
                    tail -20 /tmp/audio_test_${i}.err | sed 's/^/  /'
                fi
                if [ -f /tmp/audio_test_${i}.json ]; then
                    echo "JSON error field:"
                    python3 -c "import sys, json; f=open('/tmp/audio_test_${i}.json'); d=json.load(f); print('  ' + str(d.get('audio_analysis',{}).get('error','N/A')))" 2>/dev/null || echo "  N/A"
                fi
                echo ""
            fi
        fi
    else
        EXIT_CODE=$?
        RUN_END=$(date +%s)
        ELAPSED=$((RUN_END - RUN_START))
        
        if [ $EXIT_CODE -eq 139 ] || [ $EXIT_CODE -eq 134 ] || [ $EXIT_CODE -eq 130 ]; then
            echo "💥 CRASHED (exit code: $EXIT_CODE, ${ELAPSED}s)"
            ((CRASHES++))
            
            if [ $CRASHES -eq 1 ]; then
                echo ""
                echo "=== First Crash Details ==="
                echo "Exit code: $EXIT_CODE"
                echo "Elapsed time: ${ELAPSED}s"
                if [ -f /tmp/audio_test_${i}.err ]; then
                    echo "Stderr (last 30 lines):"
                    tail -30 /tmp/audio_test_${i}.err | sed 's/^/  /'
                fi
                echo ""
            fi
        elif grep -q "timeout\|Timeout\|TIMEOUT" /tmp/audio_test_${i}.err 2>/dev/null; then
            echo "⏱️  TIMEOUT (${ELAPSED}s)"
            ((TIMEOUTS++))
        else
            echo "❌ FAILED (exit code: $EXIT_CODE, ${ELAPSED}s)"
            ((FAILED++))
            
            if [ $FAILED -eq 1 ] && [ $CRASHES -eq 0 ]; then
                echo ""
                echo "=== First Failure Details ==="
                echo "Exit code: $EXIT_CODE"
                echo "Elapsed time: ${ELAPSED}s"
                if [ -f /tmp/audio_test_${i}.err ]; then
                    echo "Stderr (last 30 lines):"
                    tail -30 /tmp/audio_test_${i}.err | sed 's/^/  /'
                fi
                echo ""
            fi
        fi
    fi
done

END_TIME=$(date +%s)
TOTAL_ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "=========================================="
echo "Stress Test Summary"
echo "=========================================="
echo "Total runs: $RUNS"
echo "✅ Passed: $PASSED"
echo "❌ Failed: $FAILED"
echo "⏱️  Timeouts: $TIMEOUTS"
echo "💥 Crashes: $CRASHES"
echo "Total elapsed: ${TOTAL_ELAPSED}s"
echo ""

# Check for crash reports
echo "Checking for crash reports..."
CRASH_REPORTS=$(ls -t ~/Library/Logs/DiagnosticReports/Python_*.ips 2>/dev/null | head -5 || echo "")
if [ -n "$CRASH_REPORTS" ]; then
    echo "⚠️  Found crash reports:"
    echo "$CRASH_REPORTS" | head -3 | sed 's/^/  /'
else
    echo "✅ No new crash reports found"
fi

# Calculate failure rate
if [ $RUNS -gt 0 ]; then
    FAILURE_RATE=$(echo "scale=1; ($FAILED + $TIMEOUTS + $CRASHES) * 100 / $RUNS" | bc)
    echo ""
    echo "Failure rate: ${FAILURE_RATE}%"
fi

if [ $CRASHES -gt 0 ]; then
    exit 1
fi
