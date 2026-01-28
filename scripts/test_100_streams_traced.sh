#!/bin/bash
# Run 100-stream test with subprocess tracing enabled

set -e

echo "Running 100-stream test with subprocess tracing..."
echo "Logs will be captured to scratch/trace_subprocess.log"
echo ""

mkdir -p scratch

# Run with tracing enabled, capture both stdout and stderr
STREAM_CHECKER_TRACE_SUBPROCESS=1 python3 tests/test_100_streams.py > scratch/trace_subprocess.log 2>&1

# Also collect all error logs (which contain TRACE output) into the main log
# Find the most recent results directory (macOS-compatible)
RESULTS_DIR=$(ls -td /tmp/stream_test_100_results_* 2>/dev/null | head -1)
if [ -n "$RESULTS_DIR" ] && [ -d "$RESULTS_DIR" ]; then
    echo "" >> scratch/trace_subprocess.log
    echo "========================================" >> scratch/trace_subprocess.log
    echo "TRACE OUTPUT FROM INDIVIDUAL STREAM TESTS" >> scratch/trace_subprocess.log
    echo "========================================" >> scratch/trace_subprocess.log
    for error_file in "$RESULTS_DIR"/*_error.log; do
        if [ -f "$error_file" ]; then
            echo "" >> scratch/trace_subprocess.log
            echo "--- $(basename "$error_file") ---" >> scratch/trace_subprocess.log
            grep -E "(TRACE:|Subprocess tracing)" "$error_file" >> scratch/trace_subprocess.log 2>/dev/null || true
        fi
    done
fi

echo ""
echo "Test completed. Logs saved to scratch/trace_subprocess.log"
echo "File size: $(wc -l < scratch/trace_subprocess.log) lines"
echo "TRACE messages: $(grep -c "TRACE:" scratch/trace_subprocess.log 2>/dev/null || echo "0")"
