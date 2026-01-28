#!/usr/bin/env python3
"""Analyze trace log to count helper-context vs main-process-context subprocess calls"""

import re
from collections import defaultdict
from pathlib import Path
import glob
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def parse_trace_log(log_file):
    """Parse trace log and extract TRACE entries with helper context info"""
    entries = []
    
    # Try to parse from aggregated log first
    with open(log_file, 'r') as f:
        content = f.read()
        # Split by TRACE entries
        trace_blocks = re.split(r'(TRACE: subprocess\.(run|Popen) called)', content)
        
        for i in range(1, len(trace_blocks), 2):
            if i+1 < len(trace_blocks):
                trace_type = 'run' if 'subprocess.run' in trace_blocks[i] else 'Popen'
                block = trace_blocks[i+1]
                
                entry = {
                    'type': trace_type,
                    'argv': None,
                    'is_helper': None,  # True/False/None
                    'stack': []
                }
                
                # Extract argv
                argv_match = re.search(r'argv: (\[.*?\])', block)
                if argv_match:
                    try:
                        entry['argv'] = eval(argv_match.group(1))
                    except:
                        pass
                
                # Check for helper context indicators
                if 'STREAM_CHECKER_SUBPROCESS_HELPER=' in block and '(HELPER PROCESS)' in block:
                    entry['is_helper'] = True
                elif 'STREAM_CHECKER_SUBPROCESS_HELPER not set' in block and '(MAIN PROCESS)' in block:
                    entry['is_helper'] = False
                elif 'env (relevant):' in block:
                    # Check if STREAM_CHECKER_SUBPROCESS_HELPER is in the env dict
                    env_match = re.search(r'env \(relevant\): ({.*?})', block)
                    if env_match:
                        try:
                            env_dict = eval(env_match.group(1))
                            entry['is_helper'] = env_dict.get('STREAM_CHECKER_SUBPROCESS_HELPER') == '1'
                        except:
                            pass
                
                # Extract stack frames
                stack_lines = re.findall(r'File "([^"]+)", line (\d+), in (.+)', block)
                for filepath, lineno, func in stack_lines:
                    if 'subprocess_trace.py' not in filepath and 'traceback' not in filepath.lower():
                        entry['stack'].append(f'File "{filepath}", line {lineno}, in {func}')
                
                entries.append(entry)
    
    # Always parse error log files directly for complete data
    # Find results directory
    results_dirs = sorted(glob.glob("/tmp/stream_test_100_results_*"), reverse=True)
    if results_dirs:
        results_dir = Path(results_dirs[0])
        entries = []  # Replace with error log entries
        for error_file in sorted(results_dir.glob("*_error.log")):
                with open(error_file, 'r') as f:
                    content = f.read()
                    # Split by actual TRACE entries (not logger-formatted ones)
                    # Look for lines that start with "TRACE:" (not indented, not prefixed)
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
                            'argv': None,
                            'is_helper': None,
                            'stack': []
                        }
                        
                        # Extract argv
                        argv_match = re.search(r'argv: (\[.*?\])', block)
                        if argv_match:
                            try:
                                entry['argv'] = eval(argv_match.group(1))
                            except:
                                pass
                        
                        # Check for helper context - look for the env line with helper flag
                        # Pattern: "env: None (inherits os.environ), STREAM_CHECKER_SUBPROCESS_HELPER=1 (HELPER PROCESS)"
                        if 'STREAM_CHECKER_SUBPROCESS_HELPER=1' in block and '(HELPER PROCESS)' in block:
                            entry['is_helper'] = True
                        elif 'STREAM_CHECKER_SUBPROCESS_HELPER not set' in block and '(MAIN PROCESS)' in block:
                            entry['is_helper'] = False
                        elif '(HELPER PROCESS)' in block:
                            entry['is_helper'] = True
                        elif '(MAIN PROCESS)' in block:
                            entry['is_helper'] = False
                        elif 'env (relevant):' in block:
                            env_match = re.search(r'env \(relevant\): ({.*?})', block)
                            if env_match:
                                try:
                                    env_dict = eval(env_match.group(1))
                                    entry['is_helper'] = env_dict.get('STREAM_CHECKER_SUBPROCESS_HELPER') == '1'
                                except:
                                    pass
                        
                        # Extract stack frames
                        stack_lines = re.findall(r'File "([^"]+)", line (\d+), in (.+)', block)
                        for filepath, lineno, func in stack_lines:
                            if 'subprocess_trace.py' not in filepath and 'traceback' not in filepath.lower():
                                entry['stack'].append(f'File "{filepath}", line {lineno}, in {func}')
                        
                        entries.append(entry)
    
    return entries

def main():
    log_file = Path(__file__).parent.parent / "scratch" / "trace_subprocess.log"
    if not log_file.exists():
        print(f"Error: {log_file} not found")
        print("Waiting for test to complete...")
        return
    
    print("Parsing trace log...")
    entries = parse_trace_log(log_file)
    print(f"Total TRACE entries: {len(entries)}\n")
    
    # Count by context
    helper_count = sum(1 for e in entries if e['is_helper'] is True)
    main_count = sum(1 for e in entries if e['is_helper'] is False)
    unknown_count = sum(1 for e in entries if e['is_helper'] is None)
    
    print("="*80)
    print("SUBPROCESS CALL CONTEXT ANALYSIS")
    print("="*80)
    print(f"\nHelper Process Context: {helper_count} ({helper_count*100/len(entries):.1f}%)")
    print(f"Main Process Context:   {main_count} ({main_count*100/len(entries):.1f}%)")
    print(f"Unknown Context:       {unknown_count} ({unknown_count*100/len(entries):.1f}%)")
    print(f"\nTotal:                  {len(entries)}")
    
    # Break down by type
    print("\n" + "="*80)
    print("BREAKDOWN BY SUBPROCESS TYPE")
    print("="*80)
    
    for proc_type in ['run', 'Popen']:
        type_entries = [e for e in entries if e['type'] == proc_type]
        type_helper = sum(1 for e in type_entries if e['is_helper'] is True)
        type_main = sum(1 for e in type_entries if e['is_helper'] is False)
        type_unknown = sum(1 for e in type_entries if e['is_helper'] is None)
        
        print(f"\nsubprocess.{proc_type}:")
        print(f"  Helper: {type_helper} ({type_helper*100/len(type_entries):.1f}%)")
        print(f"  Main:   {type_main} ({type_main*100/len(type_entries):.1f}%)")
        print(f"  Unknown: {type_unknown}")
        print(f"  Total:  {len(type_entries)}")
    
    # Show sample callsites for main process entries
    if main_count > 0:
        print("\n" + "="*80)
        print("SAMPLE MAIN PROCESS CALLSITES (first 5 unique)")
        print("="*80)
        
        main_entries = [e for e in entries if e['is_helper'] is False]
        callsites = defaultdict(list)
        for entry in main_entries:
            sig = entry['stack'][0] if entry['stack'] else 'unknown'
            callsites[sig].append(entry)
        
        for sig, entries_list in sorted(callsites.items(), key=lambda x: len(x[1]), reverse=True)[:5]:
            entry = entries_list[0]
            print(f"\n{sig}")
            print(f"  Occurrences: {len(entries_list)}")
            if entry['argv']:
                cmd = entry['argv'][0] if entry['argv'] else 'unknown'
                print(f"  Command: {cmd}")
            print(f"  Type: subprocess.{entry['type']}")

if __name__ == '__main__':
    main()
