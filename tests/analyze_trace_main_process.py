#!/usr/bin/env python3
"""Analyze trace log to find subprocess calls executed in main process (without STREAM_CHECKER_SUBPROCESS_HELPER)"""

import re
from collections import defaultdict
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def parse_trace_log(log_file):
    """Parse trace log and extract TRACE entries"""
    entries = []
    current_entry = None
    collecting_stack = False
    stack_lines = []
    in_entry = False
    
    with open(log_file, 'r') as f:
        for line in f:
            original_line = line
            line = line.rstrip()
            
            # Look for raw TRACE line (not logger-formatted)
            if line == 'TRACE: subprocess.run called' or line == 'TRACE: subprocess.Popen called':
                if current_entry:
                    entries.append(current_entry)
                current_entry = {
                    'type': 'run' if 'subprocess.run' in line else 'Popen',
                    'argv': None,
                    'cwd': None,
                    'timeout': None,
                    'env': None,
                    'env_has_helper': None,  # True/False/None (None = env not logged)
                    'stack': []
                }
                collecting_stack = False
                stack_lines = []
                in_entry = True
                continue
            
            if not current_entry or not in_entry:
                continue
            
            # Skip logger-formatted duplicate lines - look for the actual data lines
            # These come after the logger prefix
            if 'stream_checker.subprocess_trace - ERROR -' in original_line:
                # Extract the actual content after the logger prefix
                content = original_line.split('stream_checker.subprocess_trace - ERROR -', 1)[1].strip()
                
                # Extract argv
                if content.startswith('argv:'):
                    try:
                        argv_str = content.replace('argv:', '').strip()
                        current_entry['argv'] = eval(argv_str)
                    except:
                        current_entry['argv'] = argv_str
                
                # Extract cwd
                elif content.startswith('cwd:'):
                    cwd_str = content.replace('cwd:', '').strip()
                    current_entry['cwd'] = None if cwd_str == 'None' else cwd_str
                
                # Extract timeout
                elif content.startswith('timeout:'):
                    timeout_str = content.replace('timeout:', '').strip()
                    current_entry['timeout'] = None if timeout_str == 'None' else timeout_str
                
                # Extract env
                elif content.startswith('env (relevant):'):
                    env_str = content.replace('env (relevant):', '').strip()
                    try:
                        env_dict = eval(env_str) if env_str != 'None' else {}
                        current_entry['env'] = env_dict
                        current_entry['env_has_helper'] = env_dict.get('STREAM_CHECKER_SUBPROCESS_HELPER') == '1'
                    except:
                        current_entry['env'] = {}
                        current_entry['env_has_helper'] = False
                
                # Stack trace start
                elif 'Stack trace' in content:
                    collecting_stack = True
                    continue
                
                # Collect stack frames
                elif collecting_stack:
                    if content.startswith('=' * 70):
                        # End of entry
                        current_entry['stack'] = stack_lines[:5]  # Top 5 frames
                        collecting_stack = False
                        stack_lines = []
                        in_entry = False
                    elif content.strip():
                        # Extract File line from stack frame
                        # Format: "File "/path/to/file.py", line 123, in function_name"
                        match = re.search(r'File "([^"]+)", line (\d+), in (.+)', content)
                        if match:
                            filepath = match.group(1)
                            lineno = match.group(2)
                            func = match.group(3)
                            # Skip subprocess_trace.py and traceback internals
                            if 'subprocess_trace.py' not in filepath and 'traceback' not in filepath.lower():
                                stack_lines.append(f'File "{filepath}", line {lineno}, in {func}')
                        # Also check for code context lines (indented)
                        elif content.strip().startswith((' ', '\t')) and not content.strip().startswith('File'):
                            # This is code context, skip for now
                            pass
    
    # Add last entry
    if current_entry:
        entries.append(current_entry)
    
    return entries

def get_callsite_signature(entry):
    """Extract a callsite signature from stack trace"""
    if not entry['stack']:
        return 'unknown'
    
    # Find first meaningful frame (not subprocess.py, not subprocess_trace.py)
    for frame in entry['stack']:
        if 'subprocess.py' not in frame and 'subprocess_trace.py' not in frame:
            # Extract file and function
            match = re.search(r'File "([^"]+)", line (\d+), in (.+)', frame)
            if match:
                filepath = match.group(1)
                func = match.group(3)
                # Get just the filename
                filename = Path(filepath).name
                return f"{filename}:{match.group(2)} ({func})"
            return frame
    return 'unknown'

def main():
    log_file = Path(__file__).parent.parent / "scratch" / "trace_subprocess.log"
    if not log_file.exists():
        print(f"Error: {log_file} not found")
        return
    
    print("Parsing trace log...")
    entries = parse_trace_log(log_file)
    print(f"Total TRACE entries parsed: {len(entries)}\n")
    
    # Filter entries executed in main process (no STREAM_CHECKER_SUBPROCESS_HELPER)
    main_process_entries = []
    for entry in entries:
        # If env_has_helper is False or None (env not logged/empty), it's in main process
        # If env_has_helper is True, it's in helper process
        if entry['env_has_helper'] is not True:
            main_process_entries.append(entry)
    
    print(f"Entries executed in MAIN PROCESS (no STREAM_CHECKER_SUBPROCESS_HELPER): {len(main_process_entries)}")
    print(f"Entries executed in HELPER PROCESS (has STREAM_CHECKER_SUBPROCESS_HELPER): {len(entries) - len(main_process_entries)}\n")
    
    if not main_process_entries:
        print("✅ All subprocess calls were executed in helper processes (safe)")
        return
    
    # Group by callsite
    callsites = defaultdict(list)
    for entry in main_process_entries:
        sig = get_callsite_signature(entry)
        callsites[sig].append(entry)
    
    print("="*80)
    print("SUMMARY: Subprocess calls executed in MAIN PROCESS (potential fork risk)")
    print("="*80)
    print(f"\nUnique callsites: {len(callsites)}\n")
    
    for sig, entries_list in sorted(callsites.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"\n{'='*80}")
        print(f"CALLSITE: {sig}")
        print(f"Occurrences: {len(entries_list)}")
        print(f"{'='*80}")
        
        # Show first entry as example
        entry = entries_list[0]
        print(f"\nType: subprocess.{entry['type']}")
        print(f"argv: {entry['argv']}")
        print(f"cwd: {entry['cwd']}")
        print(f"timeout: {entry['timeout']}")
        if entry['env'] is not None:
            print(f"env: {entry['env']}")
        else:
            print(f"env: None (not passed to subprocess)")
        print(f"\nTop 5 stack frames:")
        for i, frame in enumerate(entry['stack'][:5], 1):
            print(f"  {i}. {frame}")
        
        # Show unique argv patterns
        unique_argv = set()
        for e in entries_list[:10]:  # Sample first 10
            if e['argv']:
                argv_str = ' '.join(str(x) for x in e['argv'][:3])  # First 3 args
                unique_argv.add(argv_str)
        if len(unique_argv) > 1:
            print(f"\nSample argv patterns (first 3 args):")
            for argv_pattern in list(unique_argv)[:5]:
                print(f"  - {argv_pattern}...")

if __name__ == '__main__':
    main()
