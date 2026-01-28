#!/bin/bash
# Crash regression check for macOS - verifies no subprocess calls occur in main process
# This test prevents regression of macOS fork crashes by ensuring all subprocess
# calls go through the safe helper process mechanism.

set -e

echo "======================================================================"
echo "macOS Fork Crash Regression Test"
echo "======================================================================"
echo ""
echo "This test verifies that no subprocess calls occur in the main process"
echo "on macOS. All subprocess calls must execute in HELPER PROCESS context"
echo "to prevent fork crashes."
echo ""

# Check if running on macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "⚠️  Skipping macOS-specific test (not running on macOS)"
    exit 0
fi

# Run the test
cd "$(dirname "$0")/.."
python3 tests/test_no_main_process_subprocess.py

echo ""
echo "✅ Regression test passed - no main process subprocess calls detected"
