#!/bin/bash
# Multiprocessing consistency check script
# Ensures all multiprocessing code uses centralized helper and doesn't regress

set -e

# Use ripgrep if available, otherwise fall back to grep
if command -v rg &> /dev/null; then
    GREP_CMD="rg"
    GREP_ARGS="--type py"
else
    GREP_CMD="grep"
    GREP_ARGS="-r --include='*.py'"
fi

echo "🔍 Checking multiprocessing code consistency..."

ERRORS=0

# Check 1: _ensure_spawn_method and _mp_start_method_set should only exist in multiprocessing_utils.py
echo ""
echo "Check 1: Verifying spawn method setup is centralized..."
if [ "$GREP_CMD" = "rg" ]; then
    DUPLICATES=$($GREP_CMD "_ensure_spawn_method|_mp_start_method_set" stream_checker/ $GREP_ARGS | grep -v "multiprocessing_utils.py" || true)
else
    DUPLICATES=$($GREP_CMD "_ensure_spawn_method\|_mp_start_method_set" stream_checker/ $GREP_ARGS | grep -v "multiprocessing_utils.py" || true)
fi
if [ -n "$DUPLICATES" ]; then
    echo "❌ FAIL: Found duplicate spawn method setup outside multiprocessing_utils.py:"
    echo "$DUPLICATES"
    ERRORS=$((ERRORS + 1))
else
    echo "✅ PASS: Spawn method setup is centralized in multiprocessing_utils.py"
fi

# Check 2: No direct multiprocessing.Process( or multiprocessing.Queue( in core modules
echo ""
echo "Check 2: Verifying no direct Process/Queue creation in core modules..."
if [ "$GREP_CMD" = "rg" ]; then
    DIRECT_CREATION=$($GREP_CMD "multiprocessing\.Process\(|multiprocessing\.Queue\(" stream_checker/core/ $GREP_ARGS || true)
else
    DIRECT_CREATION=$($GREP_CMD "multiprocessing\.Process(\|multiprocessing\.Queue(" stream_checker/core/ $GREP_ARGS || true)
fi
if [ -n "$DIRECT_CREATION" ]; then
    echo "❌ FAIL: Found direct Process/Queue creation in core modules:"
    echo "$DIRECT_CREATION"
    ERRORS=$((ERRORS + 1))
else
    echo "✅ PASS: No direct Process/Queue creation in core modules"
fi

# Check 3: All 6 sites should call run_process_with_queue
echo ""
echo "Check 3: Verifying all sites use run_process_with_queue helper..."
if [ "$GREP_CMD" = "rg" ]; then
    CALL_COUNT=$($GREP_CMD "run_process_with_queue\(" stream_checker/core/ $GREP_ARGS | wc -l | tr -d ' ')
    CALL_SITES=$($GREP_CMD "run_process_with_queue\(" stream_checker/core/ $GREP_ARGS || echo "(none found)")
else
    # Use simple pattern without escaping for grep, filter out import lines
    CALL_COUNT=$(grep -r "run_process_with_queue(" stream_checker/core/ --include="*.py" | grep -v "import\|from" | wc -l | tr -d ' ')
    CALL_SITES=$(grep -r "run_process_with_queue(" stream_checker/core/ --include="*.py" | grep -v "import\|from" || echo "(none found)")
fi
if [ "$CALL_COUNT" -eq 6 ]; then
    echo "✅ PASS: Found exactly 6 call sites (expected)"
    echo "$CALL_SITES"
else
    echo "❌ FAIL: Expected 6 call sites, found $CALL_COUNT:"
    echo "$CALL_SITES"
    ERRORS=$((ERRORS + 1))
fi

# Check 4: No direct multiprocessing imports in core modules (workaround detection)
echo ""
echo "Check 4: Verifying no direct multiprocessing imports in core modules..."
if [ "$GREP_CMD" = "rg" ]; then
    DIRECT_IMPORTS=$($GREP_CMD "from multiprocessing import|import multiprocessing as mp" stream_checker/core/ $GREP_ARGS || true)
else
    DIRECT_IMPORTS=$(grep -r "from multiprocessing import\|import multiprocessing as mp" stream_checker/core/ --include="*.py" || true)
fi
if [ -n "$DIRECT_IMPORTS" ]; then
    echo "❌ FAIL: Found direct multiprocessing imports (workaround detected):"
    echo "$DIRECT_IMPORTS"
    ERRORS=$((ERRORS + 1))
else
    echo "✅ PASS: No direct multiprocessing imports in core modules"
fi

# Check 5: No Process( or Queue( patterns (broader check for direct usage)
echo ""
echo "Check 5: Verifying no Process/Queue patterns in core modules..."
if [ "$GREP_CMD" = "rg" ]; then
    PROCESS_QUEUE_PATTERNS=$($GREP_CMD "Process\(|Queue\(" stream_checker/core/ $GREP_ARGS | grep -v "run_process_with_queue\|cleanup_multiprocessing\|#\|def\|class\|import\|from" || true)
else
    PROCESS_QUEUE_PATTERNS=$(grep -r "Process(\|Queue(" stream_checker/core/ --include="*.py" | grep -v "run_process_with_queue\|cleanup_multiprocessing\|#\|def\|class\|import\|from" || true)
fi
if [ -n "$PROCESS_QUEUE_PATTERNS" ]; then
    echo "❌ FAIL: Found Process/Queue patterns (possible direct usage):"
    echo "$PROCESS_QUEUE_PATTERNS"
    ERRORS=$((ERRORS + 1))
else
    echo "✅ PASS: No Process/Queue patterns in core modules"
fi

# Summary
echo ""
if [ $ERRORS -eq 0 ]; then
    echo "✅ All multiprocessing consistency checks passed!"
    exit 0
else
    echo "❌ $ERRORS check(s) failed. Please fix the issues above."
    exit 1
fi
