"""Subprocess tracing for debugging - monkeypatches subprocess.Popen and subprocess.run"""

import os
import sys
import subprocess
import traceback
import logging
from typing import Any, Optional, Dict, List

# Create a logger that writes to stderr
logger = logging.getLogger("stream_checker.subprocess_trace")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)  # Use ERROR level so it's always shown

# Store original functions
_original_popen = subprocess.Popen
_original_run = subprocess.run


def _redact_env(env: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """Redact sensitive environment variables"""
    if env is None:
        return None
    redacted = {}
    sensitive_keys = ['PASSWORD', 'SECRET', 'KEY', 'TOKEN', 'AUTH', 'CREDENTIAL']
    for key, value in env.items():
        if any(sensitive in key.upper() for sensitive in sensitive_keys):
            redacted[key] = '<REDACTED>'
        else:
            redacted[key] = value
    return redacted


def _get_stack_trace(limit: int = 25) -> str:
    """Get formatted stack trace"""
    stack = traceback.format_stack(limit=limit)
    # Remove this module's frames from the top
    filtered = []
    skip = True
    for frame in stack:
        if 'subprocess_trace.py' not in frame or not skip:
            filtered.append(frame)
            skip = False
    return ''.join(filtered[-15:])  # Last 15 frames


def _traced_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
    """Traced version of subprocess.Popen"""
    cmd = args[0] if args else kwargs.get('args', [])
    cwd = kwargs.get('cwd', os.getcwd())
    env = kwargs.get('env', None)
    
    # Log call details
    logger.error("=" * 70)
    logger.error("TRACE: subprocess.Popen called")
    logger.error(f"  argv: {cmd}")
    logger.error(f"  cwd: {cwd}")
    redacted_env = _redact_env(env)
    if redacted_env:
        # Show only relevant env vars (STREAM_CHECKER_*, PATH, VIRTUAL_ENV)
        relevant_env = {k: v for k, v in redacted_env.items() if any(x in k for x in ['STREAM_CHECKER', 'PATH', 'VIRTUAL_ENV', 'PWD', 'HOME'])}
        logger.error(f"  env (relevant): {relevant_env}")
    else:
        # env is None - check os.environ for STREAM_CHECKER_SUBPROCESS_HELPER
        helper_flag = os.environ.get('STREAM_CHECKER_SUBPROCESS_HELPER')
        if helper_flag:
            logger.error(f"  env: None (inherits os.environ), STREAM_CHECKER_SUBPROCESS_HELPER={helper_flag} (HELPER PROCESS)")
        else:
            logger.error(f"  env: None (inherits os.environ), STREAM_CHECKER_SUBPROCESS_HELPER not set (MAIN PROCESS)")
    logger.error("  Stack trace (last 10 frames):")
    stack = _get_stack_trace(limit=25)
    for line in stack.split('\n')[-12:]:  # Last 12 lines
        if line.strip() and 'subprocess_trace.py' not in line:
            logger.error(f"    {line.rstrip()}")
    logger.error("=" * 70)
    
    # Call original
    return _original_popen(*args, **kwargs)


def _traced_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    """Traced version of subprocess.run"""
    cmd = args[0] if args else kwargs.get('args', [])
    cwd = kwargs.get('cwd', os.getcwd())
    env = kwargs.get('env', None)
    timeout = kwargs.get('timeout', None)
    
    # Log call details
    logger.error("=" * 70)
    logger.error("TRACE: subprocess.run called")
    logger.error(f"  argv: {cmd}")
    logger.error(f"  cwd: {cwd}")
    logger.error(f"  timeout: {timeout}")
    redacted_env = _redact_env(env)
    if redacted_env:
        # Show only relevant env vars
        relevant_env = {k: v for k, v in redacted_env.items() if any(x in k for x in ['STREAM_CHECKER', 'PATH', 'VIRTUAL_ENV', 'PWD', 'HOME'])}
        logger.error(f"  env (relevant): {relevant_env}")
    else:
        # env is None - check os.environ for STREAM_CHECKER_SUBPROCESS_HELPER
        helper_flag = os.environ.get('STREAM_CHECKER_SUBPROCESS_HELPER')
        if helper_flag:
            logger.error(f"  env: None (inherits os.environ), STREAM_CHECKER_SUBPROCESS_HELPER={helper_flag} (HELPER PROCESS)")
        else:
            logger.error(f"  env: None (inherits os.environ), STREAM_CHECKER_SUBPROCESS_HELPER not set (MAIN PROCESS)")
    logger.error("  Stack trace (last 10 frames):")
    stack = _get_stack_trace(limit=25)
    for line in stack.split('\n')[-12:]:  # Last 12 lines
        if line.strip() and 'subprocess_trace.py' not in line:
            logger.error(f"    {line.rstrip()}")
    logger.error("=" * 70)
    
    # Call original
    return _original_run(*args, **kwargs)


def install_tracing():
    """Install subprocess tracing monkeypatch"""
    if os.environ.get('STREAM_CHECKER_TRACE_SUBPROCESS') == '1':
        subprocess.Popen = _traced_popen
        subprocess.run = _traced_run
        logger.error("Subprocess tracing ENABLED - all subprocess.Popen/run calls will be logged")


def uninstall_tracing():
    """Uninstall subprocess tracing monkeypatch"""
    subprocess.Popen = _original_popen
    subprocess.run = _original_run
    logger.error("Subprocess tracing DISABLED")
