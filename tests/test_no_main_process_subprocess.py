#!/usr/bin/env python3
"""
Test to verify no subprocess calls occur in main process on macOS.
This prevents regression of macOS fork crashes.

When STREAM_CHECKER_TRACE_SUBPROCESS=1 is enabled, all subprocess calls
should execute in HELPER PROCESS context (via run_subprocess_safe),
not MAIN PROCESS context.
"""

import os
import sys
import subprocess
import tempfile
import re
from pathlib import Path
from collections import defaultdict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def parse_trace_from_error_logs(results_dir):
    """Parse TRACE entries from error log files and count helper vs main process calls"""
    entries = []
    results_path = Path(results_dir)
    
    if not results_path.exists():
        return entries
    
    for error_file in sorted(results_path.glob("*_error.log")):
        with open(error_file, 'r') as f:
            content = f.read()
            # Find all TRACE entries (lines starting with "TRACE:" not prefixed)
            trace_matches = list(re.finditer(r'^TRACE: subprocess\.(run|Popen) called', content, re.MULTILINE))
            
            for idx, match in enumerate(trace_matches):
                trace_type = 'run' if 'subprocess.run' in match.group(0) else 'Popen'
                start_pos = match.end()
                # Find next TRACE entry or end of file
                if idx + 1 < len(trace_matches):
                    end_pos = trace_matches[idx + 1].start()
                else:
                    end_pos = len(content)
                block = content[start_pos:end_pos]
                
                entry = {
                    'type': trace_type,
                    'is_helper': None
                }
                
                # Check for helper context markers
                if 'STREAM_CHECKER_SUBPROCESS_HELPER=1' in block and '(HELPER PROCESS)' in block:
                    entry['is_helper'] = True
                elif 'STREAM_CHECKER_SUBPROCESS_HELPER not set' in block and '(MAIN PROCESS)' in block:
                    entry['is_helper'] = False
                elif '(HELPER PROCESS)' in block:
                    entry['is_helper'] = True
                elif '(MAIN PROCESS)' in block:
                    entry['is_helper'] = False
                
                entries.append(entry)
    
    return entries


def test_no_main_process_subprocess():
    """Test that no subprocess calls occur in main process on macOS"""
    if os.name != 'posix' or sys.platform != 'darwin':
        # Skip on non-macOS systems
        return
    
    # Use a small set of test streams (5 streams)
    test_streams = [
        "http://streams.radiomast.io/ref-128k-mp3-stereo",
        "http://streams.radiomast.io/ref-96k-mp3-stereo",
        "http://streams.radiomast.io/ref-64k-mp3-stereo",
        "http://streams.radiomast.io/ref-32k-mp3-mono",
        "https://streams.radiomast.io/ref-128k-mp3-stereo",
    ]
    
    # Create temporary results directory
    with tempfile.TemporaryDirectory(prefix='stream_test_regression_') as tmpdir:
        results_dir = Path(tmpdir) / "results"
        results_dir.mkdir()
        
        # Run stream_checker.py for each test stream with tracing enabled
        project_root = Path(__file__).parent.parent
        stream_checker_script = project_root / "stream_checker.py"
        
        env = os.environ.copy()
        env['STREAM_CHECKER_TRACE_SUBPROCESS'] = '1'
        
        for i, url in enumerate(test_streams, 1):
            print(f"Testing stream {i}/{len(test_streams)}: {url}")
            result = subprocess.run(
                [sys.executable, str(stream_checker_script), "--url", url, "--output-format", "json"],
                env=env,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout per stream
            )
            
            # Save error output to results directory
            error_file = results_dir / f"stream_{i}_error.log"
            with open(error_file, 'w') as f:
                f.write(result.stderr)
            
            if result.returncode != 0:
                print(f"  Warning: Stream test returned non-zero exit code: {result.returncode}")
        
        # Parse trace entries from error logs
        entries = parse_trace_from_error_logs(results_dir)
        
        if not entries:
            raise AssertionError("No TRACE entries found - tracing may not be working")
        
        # Count helper vs main process calls
        helper_count = sum(1 for e in entries if e['is_helper'] is True)
        main_count = sum(1 for e in entries if e['is_helper'] is False)
        unknown_count = sum(1 for e in entries if e['is_helper'] is None)
        
        print(f"\nTrace Analysis:")
        print(f"  Total TRACE entries: {len(entries)}")
        print(f"  Helper Process Context: {helper_count}")
        print(f"  Main Process Context: {main_count}")
        print(f"  Unknown Context: {unknown_count}")
        
        # Assert no main process calls
        assert main_count == 0, (
            f"FAILED: Found {main_count} subprocess calls executed in MAIN PROCESS context. "
            f"This indicates a regression - subprocess calls should only occur in HELPER PROCESS "
            f"context to prevent macOS fork crashes. Helper: {helper_count}, Main: {main_count}, "
            f"Unknown: {unknown_count}"
        )
        
        # Warn if there are unknown entries (shouldn't happen with proper tracing)
        if unknown_count > 0:
            print(f"  WARNING: {unknown_count} entries with unknown context - tracing may be incomplete")
        
        print(f"\n✅ PASSED: All {len(entries)} subprocess calls executed in HELPER PROCESS context")


if __name__ == '__main__':
    try:
        test_no_main_process_subprocess()
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
