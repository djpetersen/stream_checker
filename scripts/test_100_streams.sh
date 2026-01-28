#!/bin/bash
# Comprehensive test script for 100 audio streams - tests all phases and logs to database

STREAMS=(
    # RadioMast reference streams (MP3)
    "http://streams.radiomast.io/ref-128k-mp3-stereo"
    "http://streams.radiomast.io/ref-96k-mp3-stereo"
    "http://streams.radiomast.io/ref-64k-mp3-stereo"
    "http://streams.radiomast.io/ref-32k-mp3-mono"
    "https://streams.radiomast.io/ref-128k-mp3-stereo"
    "https://streams.radiomast.io/ref-96k-mp3-stereo"
    
    # RadioMast AAC streams
    "http://streams.radiomast.io/ref-128k-aaclc-stereo"
    "http://streams.radiomast.io/ref-96k-aaclc-stereo"
    "http://streams.radiomast.io/ref-64k-heaacv1-stereo"
    "http://streams.radiomast.io/ref-64k-heaacv2-stereo"
    "http://streams.radiomast.io/ref-24k-heaacv1-mono"
    "https://streams.radiomast.io/ref-128k-aaclc-stereo"
    
    # RadioMast Ogg streams
    "http://streams.radiomast.io/ref-64k-ogg-vorbis-stereo"
    "http://streams.radiomast.io/ref-64k-ogg-opus-stereo"
    "http://streams.radiomast.io/ref-96k-ogg-vorbis-stereo"
    
    # Dutch public radio (Icecast) - NPO Radio
    "http://icecast.omroep.nl/radio1-bb-mp3"
    "http://icecast.omroep.nl/radio2-bb-mp3"
    "http://icecast.omroep.nl/3fm-bb-mp3"
    "http://icecast.omroep.nl/radio4-bb-mp3"
    "http://icecast.omroep.nl/radio5-bb-mp3"
    "http://icecast.omroep.nl/radio6-bb-mp3"
    "http://icecast.omroep.nl/funx-bb-mp3"
    
    # SomaFM streams (MP3)
    "http://ice1.somafm.com/groovesalad-128-mp3"
    "http://ice1.somafm.com/dronezone-128-mp3"
    "http://ice1.somafm.com/deepspaceone-128-mp3"
    "http://ice1.somafm.com/defcon-128-mp3"
    "http://ice1.somafm.com/fluid-128-mp3"
    "http://ice1.somafm.com/beatblender-128-mp3"
    "http://ice1.somafm.com/bootliquor-128-mp3"
    "http://ice1.somafm.com/brfm-128-mp3"
    "http://ice1.somafm.com/christmas-128-mp3"
    "http://ice1.somafm.com/cliqhop-128-mp3"
    "http://ice1.somafm.com/covers-128-mp3"
    "http://ice1.somafm.com/deepspaceone-128-mp3"
    "http://ice1.somafm.com/digitalis-128-mp3"
    "http://ice1.somafm.com/doomed-128-mp3"
    "http://ice1.somafm.com/dubstep-128-mp3"
    "http://ice1.somafm.com/earwaves-128-mp3"
    "http://ice1.somafm.com/folkfwd-128-mp3"
    "http://ice1.somafm.com/groovesalad-128-mp3"
    "http://ice1.somafm.com/illstreet-128-mp3"
    "http://ice1.somafm.com/indiepop-128-mp3"
    "http://ice1.somafm.com/lush-128-mp3"
    "http://ice1.somafm.com/metal-128-mp3"
    "http://ice1.somafm.com/missioncontrol-128-mp3"
    "http://ice1.somafm.com/n5md-128-mp3"
    "http://ice1.somafm.com/poptron-128-mp3"
    "http://ice1.somafm.com/reggae-128-mp3"
    "http://ice1.somafm.com/seventies-128-mp3"
    "http://ice1.somafm.com/sf1033-128-mp3"
    "http://ice1.somafm.com/sonicuniverse-128-mp3"
    "http://ice1.somafm.com/spacestation-128-mp3"
    "http://ice1.somafm.com/suburbsofgoa-128-mp3"
    "http://ice1.somafm.com/synphaera-128-mp3"
    "http://ice1.somafm.com/thetrip-128-mp3"
    "http://ice1.somafm.com/thistle-128-mp3"
    "http://ice1.somafm.com/u80s-128-mp3"
    "http://ice1.somafm.com/vaporwaves-128-mp3"
    "http://ice2.somafm.com/beatblender-128-mp3"
    "http://ice2.somafm.com/bootliquor-128-mp3"
    "http://ice2.somafm.com/brfm-128-mp3"
    "http://ice2.somafm.com/cliqhop-128-mp3"
    "http://ice2.somafm.com/covers-128-mp3"
    "http://ice2.somafm.com/deepspaceone-128-mp3"
    "http://ice2.somafm.com/digitalis-128-mp3"
    "http://ice2.somafm.com/doomed-128-mp3"
    "http://ice2.somafm.com/dronezone-128-mp3"
    "http://ice2.somafm.com/earwaves-128-mp3"
    "http://ice2.somafm.com/folkfwd-128-mp3"
    "http://ice2.somafm.com/groovesalad-128-mp3"
    "http://ice2.somafm.com/illstreet-128-mp3"
    "http://ice2.somafm.com/indiepop-128-mp3"
    "http://ice2.somafm.com/lush-128-mp3"
    "http://ice2.somafm.com/metal-128-mp3"
    "http://ice2.somafm.com/missioncontrol-128-mp3"
    "http://ice2.somafm.com/n5md-128-mp3"
    "http://ice2.somafm.com/poptron-128-mp3"
    "http://ice2.somafm.com/reggae-128-mp3"
    "http://ice2.somafm.com/seventies-128-mp3"
    "http://ice2.somafm.com/sf1033-128-mp3"
    "http://ice2.somafm.com/sonicuniverse-128-mp3"
    "http://ice2.somafm.com/spacestation-128-mp3"
    "http://ice2.somafm.com/suburbsofgoa-128-mp3"
    "http://ice2.somafm.com/synphaera-128-mp3"
    "http://ice2.somafm.com/thetrip-128-mp3"
    "http://ice2.somafm.com/thistle-128-mp3"
    "http://ice2.somafm.com/u80s-128-mp3"
    "http://ice2.somafm.com/vaporwaves-128-mp3"
    
    # Radio France (HTTPS)
    "https://icecast.radiofrance.fr/fip-hifi.mp3"
    "https://icecast.radiofrance.fr/franceinter-hifi.aac"
    "https://icecast.radiofrance.fr/franceinfo-hifi.aac"
    "https://icecast.radiofrance.fr/franceculture-hifi.aac"
    "https://icecast.radiofrance.fr/francemusique-hifi.aac"
    "https://icecast.radiofrance.fr/mouv-hifi.aac"
    "https://icecast.radiofrance.fr/fip-hifi.aac"
    
    # BBC Radio streams
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio1_mf_p"
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio2_mf_p"
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio3_mf_p"
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio4fm_mf_p"
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio5live_mf_p"
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_6music_mf_p"
    
    # Additional public radio streams
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_one"
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_two"
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_three"
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_fourfm"
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_five_live_online_nonuk"
    "http://stream.live.vc.bbcmedia.co.uk/bbc_6music"
    
    # HLS test streams (M3U8)
    "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"
    "https://devstreaming-cdn.apple.com/videos/streaming/examples/img_bipbop_adv_example_fmp4/master.m3u8"
    "https://demo.unified-streaming.com/k8s/features/stable/video/tears-of-steel/tears-of-steel.ism/.m3u8"
    
    # Radio Paradise streams (MP3 and AAC)
    "http://stream-dc1.radioparadise.com/mp3-192"
    "http://stream-dc1.radioparadise.com/mp3-128"
    "http://stream-tx1.radioparadise.com/mp3-128"
    "http://stream-dc1.radioparadise.com/mp3-32"
    "http://stream-dc1.radioparadise.com/aac-320"
    "http://stream-dc1.radioparadise.com/aac-128"
    "http://stream-tx1.radioparadise.com/aac-64"
    "http://stream-tx1.radioparadise.com/aac-32"
    
    # WFMU streams
    "http://stream0.wfmu.org/freeform-128k"
    "http://stream0.wfmu.org/rock-128k"
    "http://stream0.wfmu.org/teaparty-128k"
    
    # Additional SomaFM streams (different servers)
    "http://ice3.somafm.com/groovesalad-128-mp3"
    "http://ice3.somafm.com/dronezone-128-mp3"
    "http://ice3.somafm.com/deepspaceone-128-mp3"
    "http://ice3.somafm.com/beatblender-128-mp3"
    "http://ice3.somafm.com/bootliquor-128-mp3"
    "http://ice4.somafm.com/groovesalad-128-mp3"
    "http://ice4.somafm.com/dronezone-128-mp3"
    "http://ice4.somafm.com/deepspaceone-128-mp3"
    "http://ice5.somafm.com/groovesalad-128-mp3"
    "http://ice5.somafm.com/dronezone-128-mp3"
    "http://ice5.somafm.com/beatblender-128-mp3"
    "http://ice6.somafm.com/groovesalad-128-mp3"
    "http://ice6.somafm.com/dronezone-128-mp3"
    "http://ice6.somafm.com/deepspaceone-128-mp3"
    
    # Additional RadioMast streams (different bitrates)
    "http://streams.radiomast.io/ref-48k-mp3-stereo"
    "http://streams.radiomast.io/ref-40k-mp3-stereo"
    "https://streams.radiomast.io/ref-64k-mp3-stereo"
    "https://streams.radiomast.io/ref-32k-mp3-mono"
    "https://streams.radiomast.io/ref-128k-aaclc-stereo"
    "https://streams.radiomast.io/ref-64k-heaacv1-stereo"
    "https://streams.radiomast.io/ref-64k-ogg-vorbis-stereo"
    "https://streams.radiomast.io/ref-64k-ogg-opus-stereo"
    
    # Additional Dutch radio streams
    "http://icecast.omroep.nl/radio1-bb-aac"
    "http://icecast.omroep.nl/radio2-bb-aac"
    "http://icecast.omroep.nl/3fm-bb-aac"
    
    # Additional Radio France streams
    "https://icecast.radiofrance.fr/fip-midfi.mp3"
    "https://icecast.radiofrance.fr/franceinter-midfi.aac"
    "https://icecast.radiofrance.fr/franceinfo-midfi.aac"
    "https://icecast.radiofrance.fr/franceculture-midfi.aac"
    
    # Additional BBC streams
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio1xtra_mf_p"
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio4extra_mf_p"
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_asiannetwork_mf_p"
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_worldservice_mf_p"
    
    # Additional HLS streams
    "https://cph-p2p-msl.akamaized.net/hls/live/2000345/test/master.m3u8"
    "https://bitdash-a.akamaihd.net/content/sintel/hls/playlist.m3u8"
    
    # Additional public radio streams
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_onextra"
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_four_extra"
    "http://stream.live.vc.bbcmedia.co.uk/bbc_asian_network"
    "http://stream.live.vc.bbcmedia.co.uk/bbc_world_service"
)

PASSED=0
FAILED=0
CRASHED=0
FAILED_STREAMS=()
CRASHED_STREAMS=()
START_TIME=$(date +%s)

echo "=========================================="
echo "Comprehensive Stream Test Suite - 100 Streams"
echo "Testing ${#STREAMS[@]} audio streams"
echo "Running ALL phases (including VLC player test)"
echo "Results will be logged to database"
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
RESULTS_DIR="/tmp/stream_test_100_results_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

# Verify database path
DB_PATH="$HOME/.stream_checker/stream_checker.db"
echo "Database location: $DB_PATH"
if [ ! -f "$DB_PATH" ]; then
    echo "Database will be created on first test run"
else
    echo "✅ Database exists"
fi
echo ""

for i in "${!STREAMS[@]}"; do
    URL="${STREAMS[$i]}"
    NUM=$((i + 1))
    RESULT_FILE="$RESULTS_DIR/stream_${NUM}.json"
    ERROR_FILE="$RESULTS_DIR/stream_${NUM}_error.log"
    
    echo "[$NUM/${#STREAMS[@]}] Testing: $URL"
    echo "----------------------------------------"
    
    # Run comprehensive test (all phases) - results automatically logged to database
    if $PYTHON_CMD stream_checker.py --url "$URL" --output-format json > "$RESULT_FILE" 2>"$ERROR_FILE"; then
        # Check if output is valid JSON and contains test_run_id
        if grep -q "test_run_id" "$RESULT_FILE" 2>/dev/null; then
            echo "✅ PASSED - All phases completed, logged to database"
            ((PASSED++))
            
            # Extract key metrics if jq is available
            if command -v jq &> /dev/null; then
                HEALTH=$(jq -r '.health_score // "N/A"' "$RESULT_FILE" 2>/dev/null)
                STATUS=$(jq -r '.connectivity.status // "N/A"' "$RESULT_FILE" 2>/dev/null)
                PHASE=$(jq -r '.phase // "N/A"' "$RESULT_FILE" 2>/dev/null)
                echo "  Health Score: $HEALTH | Status: $STATUS | Phase: $PHASE"
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
                sed -n '1,20p' "$ERROR_FILE"
            fi
        else
            echo "❌ FAILED (exit code: $EXIT_CODE)"
            ((FAILED++))
            FAILED_STREAMS+=("$URL")
            
            # Show error details from error log
            if [ -f "$ERROR_FILE" ] && [ -s "$ERROR_FILE" ]; then
                echo "  Error output (see $ERROR_FILE for full details):"
                sed -n '1,20p' "$ERROR_FILE"
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

# Verify database has results
if [ -f "$DB_PATH" ]; then
    echo "Verifying database results..."
    DB_COUNT=$($PYTHON_CMD -c "
import sqlite3
conn = sqlite3.connect('$DB_PATH')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM test_runs')
count = cursor.fetchone()[0]
print(count)
conn.close()
" 2>/dev/null || echo "0")
    echo "Test runs in database: $DB_COUNT"
    echo ""
fi

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
echo "Database location: $DB_PATH"
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
