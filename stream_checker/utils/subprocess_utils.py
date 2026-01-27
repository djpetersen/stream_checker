"""Safe subprocess execution utilities that prevent fork crashes on macOS"""

import os
import platform
import subprocess
import multiprocessing
from typing import Dict, Any, Optional, List, Union
import logging

logger = logging.getLogger("stream_checker")

# Ensure spawn method is set on macOS before any multiprocessing operations
_mp_start_method_set = False


def _ensure_spawn_method():
    """Ensure multiprocessing uses spawn method on macOS"""
    global _mp_start_method_set
    if _mp_start_method_set:
        return
    
    if platform.system() == "Darwin":
        if not hasattr(multiprocessing, 'get_start_method'):
            _mp_start_method_set = True
            return
        
        try:
            current_method = multiprocessing.get_start_method(allow_none=True)
            if current_method is None:
                try:
                    multiprocessing.set_start_method('spawn')
                    _mp_start_method_set = True
                except RuntimeError:
                    _mp_start_method_set = True
            elif current_method == 'spawn':
                _mp_start_method_set = True
            else:
                try:
                    multiprocessing.set_start_method('spawn', force=True)
                    _mp_start_method_set = True
                except RuntimeError:
                    _mp_start_method_set = True
        except RuntimeError:
            _mp_start_method_set = True
        except Exception as e:
            logger.debug(f"Error setting spawn method: {e}")
            _mp_start_method_set = True
    else:
        _mp_start_method_set = True


def _subprocess_worker_pipe(conn, cmd: List[str], timeout: float, cwd: Optional[str], env: Optional[Dict[str, str]], text: bool):
    """Worker function that runs subprocess in spawned process - must be at module level for pickling"""
    result = None
    try:
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            cwd=cwd,
            env=env,
            text=text
        )
        result = {
            'returncode': process.returncode,
            'stdout': process.stdout,
            'stderr': process.stderr,
            'success': True
        }
    except subprocess.TimeoutExpired as e:
        result = {
            'returncode': None,
            'stdout': None,
            'stderr': e.stderr if hasattr(e, 'stderr') else None,
            'success': False,
            'error': 'timeout',
            'timeout': timeout
        }
    except Exception as e:
        result = {
            'returncode': None,
            'stdout': None,
            'stderr': None,
            'success': False,
            'error': str(e)
        }
    finally:
        try:
            conn.send(result)
        except Exception:
            pass
        finally:
            conn.close()


def _classify_returncode(returncode: Optional[int]) -> Dict[str, Any]:
    """
    Classify subprocess return code to detect signal kills.
    
    Returns dict with:
    - 'signal_num': signal number if killed by signal, None otherwise
    - 'signal_name': human-readable signal name (e.g., 'SIGSEGV')
    - 'is_signal_kill': bool indicating if process was killed by signal
    """
    if returncode is None:
        return {
            'signal_num': None,
            'signal_name': None,
            'is_signal_kill': False
        }
    
    signal_num = None
    
    # Check for negative return code (some systems return -signal_number)
    if returncode < 0:
        signal_num = -returncode
    # Check for Unix shell convention (128 + signal_number)
    elif returncode >= 128:
        signal_num = returncode - 128
    
    if signal_num is not None:
        signal_names = {
            1: 'SIGHUP',
            2: 'SIGINT',
            3: 'SIGQUIT',
            6: 'SIGABRT',
            9: 'SIGKILL',
            11: 'SIGSEGV',
            15: 'SIGTERM'
        }
        signal_name = signal_names.get(signal_num, f'SIG{signal_num}')
        return {
            'signal_num': signal_num,
            'signal_name': signal_name,
            'is_signal_kill': True
        }
    
    return {
        'signal_num': None,
        'signal_name': None,
        'is_signal_kill': False
    }


def run_subprocess_safe(
    cmd: List[str],
    timeout: float,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    text: bool = False
) -> Dict[str, Any]:
    """
    Safely run a subprocess command, preventing fork crashes on macOS.
    
    On macOS: Runs subprocess.run() inside a spawned helper process using
    multiprocessing spawn context, returns result via Pipe (avoids Queue semaphores).
    
    On non-macOS: Calls subprocess.run() directly.
    
    Args:
        cmd: Command to run as list of strings
        timeout: Timeout in seconds
        cwd: Working directory (optional)
        env: Environment variables dict (optional)
        text: If True, return stdout/stderr as strings instead of bytes
        
    Returns:
        Dict with CompletedProcess-like fields:
        - 'returncode': int or None
        - 'stdout': bytes or str (depending on text parameter)
        - 'stderr': bytes or str (depending on text parameter)
        - 'success': bool (True if subprocess.run() completed without exception)
        - 'signal_num': int or None (signal number if killed by signal)
        - 'signal_name': str or None (human-readable signal name)
        - 'is_signal_kill': bool (True if process was killed by signal)
        - 'error': str or None (error message if subprocess.run() raised exception)
        - 'timeout': float or None (timeout value if TimeoutExpired)
    """
    if platform.system() == "Darwin":
        # macOS: Use multiprocessing spawn to avoid fork crash
        _ensure_spawn_method()
        
        parent_conn = None
        child_conn = None
        process_obj = None
        
        try:
            # Create Pipe (one-way: parent receives, child sends)
            parent_conn, child_conn = multiprocessing.Pipe(duplex=False)
            
            # Create process
            process_obj = multiprocessing.Process(
                target=_subprocess_worker_pipe,
                args=(child_conn, cmd, timeout, cwd, env, text)
            )
            
            # Start process
            process_obj.start()
            # Close child end in parent process
            child_conn.close()
            
            # Wait for process with timeout (add buffer for process overhead)
            process_obj.join(timeout=timeout + 5.0)
            
            # Check if process timed out
            if process_obj.is_alive():
                process_obj.terminate()
                process_obj.join(timeout=2.0)
                if process_obj.is_alive():
                    process_obj.kill()
                    process_obj.join()
                return {
                    'returncode': None,
                    'stdout': None,
                    'stderr': None,
                    'success': False,
                    'error': 'multiprocessing worker timeout',
                    'signal_num': None,
                    'signal_name': None,
                    'is_signal_kill': False
                }
            
            # Check process exit code for signals or errors
            exitcode = process_obj.exitcode
            if exitcode is not None and exitcode != 0:
                # Worker process crashed - classify the signal
                signal_info = _classify_returncode(exitcode)
                return {
                    'returncode': None,
                    'stdout': None,
                    'stderr': None,
                    'success': False,
                    'error': f'multiprocessing worker crashed with exitcode {exitcode}',
                    **signal_info
                }
            
            # Get result from pipe
            try:
                if parent_conn.poll():
                    result = parent_conn.recv()
                    if result:
                        # Classify returncode for signal kills
                        signal_info = _classify_returncode(result.get('returncode'))
                        result.update(signal_info)
                        return result
                else:
                    # No data in pipe - process may have crashed
                    return {
                        'returncode': None,
                        'stdout': None,
                        'stderr': None,
                        'success': False,
                        'error': 'no result from multiprocessing worker',
                        'signal_num': None,
                        'signal_name': None,
                        'is_signal_kill': False
                    }
            except Exception as e:
                logger.debug(f"Error receiving from pipe: {e}")
                return {
                    'returncode': None,
                    'stdout': None,
                    'stderr': None,
                    'success': False,
                    'error': f'error receiving result: {e}',
                    'signal_num': None,
                    'signal_name': None,
                    'is_signal_kill': False
                }
        
        except Exception as e:
            logger.debug(f"Error in run_subprocess_safe (macOS): {e}")
            return {
                'returncode': None,
                'stdout': None,
                'stderr': None,
                'success': False,
                'error': str(e),
                'signal_num': None,
                'signal_name': None,
                'is_signal_kill': False
            }
        
        finally:
            # Clean up resources
            if parent_conn:
                try:
                    parent_conn.close()
                except Exception:
                    pass
            if process_obj:
                try:
                    if process_obj.is_alive():
                        process_obj.terminate()
                        process_obj.join(timeout=1.0)
                        if process_obj.is_alive():
                            process_obj.kill()
                            process_obj.join()
                except Exception:
                    pass
    else:
        # Non-macOS: Use subprocess.run() directly
        try:
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                cwd=cwd,
                env=env,
                text=text
            )
            # Classify returncode for signal kills
            signal_info = _classify_returncode(process.returncode)
            return {
                'returncode': process.returncode,
                'stdout': process.stdout,
                'stderr': process.stderr,
                'success': True,
                **signal_info
            }
        except subprocess.TimeoutExpired as e:
            return {
                'returncode': None,
                'stdout': None,
                'stderr': e.stderr if hasattr(e, 'stderr') else None,
                'success': False,
                'error': 'timeout',
                'timeout': timeout,
                'signal_num': None,
                'signal_name': None,
                'is_signal_kill': False
            }
        except Exception as e:
            return {
                'returncode': None,
                'stdout': None,
                'stderr': None,
                'success': False,
                'error': str(e),
                'signal_num': None,
                'signal_name': None,
                'is_signal_kill': False
            }
