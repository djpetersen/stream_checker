#!/usr/bin/env bash
# Run Phase 3 for one URL with STREAM_CHECKER_AUDIO_DEBUG=1 and save logs to scratch/audio_debug_<timestamp>.log

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
URL="${1:?Usage: $0 <stream_url>}"

mkdir -p "$PROJECT_ROOT/scratch"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$PROJECT_ROOT/scratch/audio_debug_${TIMESTAMP}.log"

echo "Probing URL: $URL"
echo "Log file: $LOG_FILE"
echo ""

cd "$PROJECT_ROOT"
PYTHONPATH=. STREAM_CHECKER_AUDIO_DEBUG=1 python3 stream_checker.py --url "$URL" --phase 3 --output-format json 2>&1 | tee "$LOG_FILE"

echo ""
echo "Log saved to $LOG_FILE"
