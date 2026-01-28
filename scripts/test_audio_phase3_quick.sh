#!/bin/bash
# Quick Phase 3 stress test - 10 iterations with detailed logging

TEST_URL="http://streams.radiomast.io/ref-128k-mp3-stereo"
RUNS=10
PASSED=0
FAILED=0

echo "Phase 3 Audio Analysis Quick Test (10 runs)"
echo "=========================================="
echo ""

for i in $(seq 1 $RUNS); do
    echo -n "[$i/$RUNS] "
    START=$(date +%s)
    
    python3 stream_checker.py --url "$TEST_URL" --phase 3 --output-format json > /tmp/audio_quick_${i}.json 2>/tmp/audio_quick_${i}.err
    
    EXIT_CODE=$?
    END=$(date +%s)
    ELAPSED=$((END - START))
    
    if [ $EXIT_CODE -eq 0 ]; then
        ERROR=$(python3 -c "import sys, json; f=open('/tmp/audio_quick_${i}.json'); d=json.load(f); print(d.get('audio_analysis',{}).get('error','None'))" 2>/dev/null || echo "ParseError")
        if [ "$ERROR" = "None" ]; then
            echo "✅ PASSED (${ELAPSED}s)"
            ((PASSED++))
        else
            echo "❌ FAILED: $ERROR (${ELAPSED}s)"
            ((FAILED++))
            
            if [ $FAILED -eq 1 ]; then
                echo ""
                echo "=== First Failure ==="
                echo "Elapsed: ${ELAPSED}s"
                echo "Error: $ERROR"
                echo "Stderr (ffmpeg/timeout lines):"
                grep -E "(ffmpeg|timeout|ERROR|argv)" /tmp/audio_quick_${i}.err | tail -10 | sed 's/^/  /'
                echo ""
            fi
        fi
    else
        echo "❌ EXIT CODE $EXIT_CODE (${ELAPSED}s)"
        ((FAILED++))
    fi
done

echo ""
echo "Summary: $PASSED passed, $FAILED failed out of $RUNS runs"
