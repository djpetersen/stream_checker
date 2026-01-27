#!/bin/bash
# Comprehensive test script for 20 audio streams - tests all phases including VLC

STREAMS=(
    # RadioMast test streams (various formats)
    "http://streams.radiomast.io/ref-128k-mp3-stereo"
    "http://streams.radiomast.io/ref-32k-mp3-mono"
    "http://streams.radiomast.io/ref-128k-aaclc-stereo"
    "http://streams.radiomast.io/ref-64k-heaacv1-stereo"
    "http://streams.radiomast.io/ref-64k-ogg-vorbis-stereo"
    "http://streams.radiomast.io/ref-64k-ogg-opus-stereo"
    
    # Dutch public radio (Icecast)
    "http://icecast.omroep.nl/radio1-bb-mp3"
    "http://icecast.omroep.nl/radio2-bb-mp3"
    "http://icecast.omroep.nl/3fm-bb-mp3"
    
    # SomaFM streams
    "http://ice1.somafm.com/groovesalad-128-mp3"
    "http://ice1.somafm.com/dronezone-128-mp3"
    "http://ice1.somafm.com/deepspaceone-128-mp3"
    "http://ice2.somafm.com/beatblender-128-mp3"
    
    # Radio France (HTTPS)
    "https://icecast.radiofrance.fr/fip-hifi.mp3"
    "https://icecast.radiofrance.fr/franceinter-hifi.aac"
    
    # BBC Radio streams
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio1_mf_p"
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio2_mf_p"
    
    # Additional test streams
    "http://streams.radiomast.io/ref-96k-mp3-stereo"
    "http://ice1.somafm.com/defcon-128-mp3"
    "http://ice1.somafm.com/fluid-128-mp3"
)

PASSED=0
FAILED=0
CRASHED=0
FAILED_STREAMS=()
CRASHED_STREAMS=()
START_TIME=$(date +%s)

echo "=========================================="
echo "Comprehensive Stream Test Suite"
echo "Testing ${#STREAMS[@]} audio streams"
echo "Running ALL phases (including VLC player test)"
echo "=========================================="
echo "Start time: $(date)"
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
    PYTHON_CMD="python"
    echo "✅ Using virtual environment"
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    PYTHON_CMD="python"
    echo "✅ Using virtual environment"
else
    PYTHON_CMD="python3"
    echo "⚠️  No virtual environment found, using system Python"
fi

# Check if dependencies are installed
echo "Checking dependencies..."
if ! $PYTHON_CMD -c "import requests" 2>/dev/null; then
    echo "⚠️  Dependencies not installed. Installing from requirements.txt..."
    if $PYTHON_CMD -m pip install -q -r requirements.txt 2>/dev/null; then
        echo "✅ Dependencies installed"
    else
        echo "❌ Failed to install dependencies automatically."
        echo "   Please install manually:"
        echo "   source venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
else
    echo "✅ Dependencies already installed"
fi
echo ""

# Create results directory
RESULTS_DIR="/tmp/stream_test_results_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

for i in "${!STREAMS[@]}"; do
    URL="${STREAMS[$i]}"
    NUM=$((i + 1))
    RESULT_FILE="$RESULTS_DIR/stream_${NUM}.json"
    ERROR_FILE="$RESULTS_DIR/stream_${NUM}_error.log"
    
    echo "[$NUM/${#STREAMS[@]}] Testing: $URL"
    echo "----------------------------------------"
    
    # Run comprehensive test (all phases)
    # The application has its own timeouts configured
    if $PYTHON_CMD stream_checker.py --url "$URL" --output-format json > "$RESULT_FILE" 2>"$ERROR_FILE"; then
        # Check if output is valid JSON and contains test_run_id
        if grep -q "test_run_id" "$RESULT_FILE" 2>/dev/null; then
            echo "✅ PASSED - All phases completed"
            ((PASSED++))
            
            # Extract key metrics if jq is available
            if command -v jq &> /dev/null; then
                HEALTH=$(jq -r '.health_score // "N/A"' "$RESULT_FILE" 2>/dev/null)
                STATUS=$(jq -r '.status // "N/A"' "$RESULT_FILE" 2>/dev/null)
                echo "  Health Score: $HEALTH"
                echo "  Status: $STATUS"
            fi
        else
            echo "⚠️  WARNING - Completed but output may be invalid"
            ((FAILED++))
            FAILED_STREAMS+=("$URL")
        fi
    else
        EXIT_CODE=$?
        
        # Check if it was a crash (exit code 139 = SIGSEGV, 134 = SIGABRT)
        if [ $EXIT_CODE -eq 139 ] || [ $EXIT_CODE -eq 134 ] || [ $EXIT_CODE -eq 130 ]; then
            echo "💥 CRASHED (exit code: $EXIT_CODE)"
            ((CRASHED++))
            CRASHED_STREAMS+=("$URL")
            
            # Show crash details from error log
            if [ -f "$ERROR_FILE" ] && [ -s "$ERROR_FILE" ]; then
                echo "  Error output (see $ERROR_FILE for full details):"
                # Show error file contents (full file, not truncated)
                cat "$ERROR_FILE"
            fi
        else
            echo "❌ FAILED (exit code: $EXIT_CODE)"
            ((FAILED++))
            FAILED_STREAMS+=("$URL")
            
            # Show error details from error log
            if [ -f "$ERROR_FILE" ] && [ -s "$ERROR_FILE" ]; then
                echo "  Error output (see $ERROR_FILE for full details):"
                # Show error file contents (full file, not truncated)
                cat "$ERROR_FILE"
            fi
        fi
    fi
    echo ""
done

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo "Total streams tested: ${#STREAMS[@]}"
echo "✅ Passed: $PASSED"
echo "❌ Failed: $FAILED"
echo "💥 Crashed: $CRASHED"
echo "Duration: ${DURATION}s ($(($DURATION / 60))m $(($DURATION % 60))s)"
echo "End time: $(date)"
echo ""

if [ $CRASHED -gt 0 ]; then
    echo "⚠️  CRITICAL: $CRASHED stream(s) caused Python to crash!"
    echo "Crashed streams:"
    for stream in "${CRASHED_STREAMS[@]}"; do
        echo "  💥 $stream"
    done
    echo ""
fi

if [ $FAILED -gt 0 ]; then
    echo "Failed streams:"
    for stream in "${FAILED_STREAMS[@]}"; do
        echo "  ❌ $stream"
    done
    echo ""
fi

echo "Detailed results saved to: $RESULTS_DIR"
echo ""

# Final status
if [ $CRASHED -gt 0 ]; then
    echo "❌ TEST SUITE FAILED - Crashes detected!"
    exit 2
elif [ $FAILED -gt 0 ]; then
    echo "⚠️  TEST SUITE COMPLETED WITH FAILURES"
    exit 1
else
    echo "✅ ALL TESTS PASSED!"
    exit 0
fi
