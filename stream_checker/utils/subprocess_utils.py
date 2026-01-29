"""Safe subprocess execution utilities that prevent fork crashes on macOS"""

import os
import platform
import subprocess
import multiprocessing
import tempfile
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
    # Set env var in os.environ so nested run_subprocess_safe calls can detect we're in a helper process
    # This prevents nested spawn timeouts when run_subprocess_safe is called from within the helper
    os.environ['STREAM_CHECKER_SUBPROCESS_HELPER'] = '1'
    
    # Merge env var into env dict if provided (for subprocess.run calls)
    if env is not None:
        env['STREAM_CHECKER_SUBPROCESS_HELPER'] = '1'
    else:
        # If no env dict provided, create one with the helper flag
        env = {'STREAM_CHECKER_SUBPROCESS_HELPER': '1'}
    
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


def _subprocess_worker_stdout_to_file(
    conn,
    cmd: List[str],
    timeout: float,
    cwd: Optional[str],
    env: Optional[Dict[str, str]],
    text: bool,
    stdout_file_path: str,
):
    """Worker that runs subprocess with stdout written to a file; sends (returncode, stderr, path, size) back."""
    os.environ['STREAM_CHECKER_SUBPROCESS_HELPER'] = '1'
    if env is not None:
        env = dict(env)
        env['STREAM_CHECKER_SUBPROCESS_HELPER'] = '1'
    else:
        env = {'STREAM_CHECKER_SUBPROCESS_HELPER': '1'}
    result = None
    try:
        with open(stdout_file_path, 'wb') as fout:
            process = subprocess.run(
                cmd,
                stdout=fout,
                stderr=subprocess.PIPE,
                timeout=timeout,
                cwd=cwd,
                env=env,
                text=text
            )
        size = os.path.getsize(stdout_file_path) if os.path.exists(stdout_file_path) else 0
        result = {
            'returncode': process.returncode,
            'stdout': None,
            'stdout_path': stdout_file_path,
            'stdout_size': size,
            'stderr': process.stderr,
            'success': True
        }
    except subprocess.TimeoutExpired as e:
        size = os.path.getsize(stdout_file_path) if os.path.exists(stdout_file_path) else 0
        result = {
            'returncode': None,
            'stdout': None,
            'stdout_path': stdout_file_path,
            'stdout_size': size,
            'stderr': e.stderr if hasattr(e, 'stderr') else None,
            'success': False,
            'error': 'timeout',
            'timeout': timeout
        }
    except Exception as e:
        result = {
            'returncode': None,
            'stdout': None,
            'stdout_path': stdout_file_path,
            'stdout_size': 0,
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
    text: bool = False,
    stdout_to_file: bool = False
) -> Dict[str, Any]:
    """
    Safely run a subprocess command, preventing fork crashes on macOS.
    
    On macOS: Runs subprocess.run() inside a spawned helper process using
    multiprocessing spawn context, returns result via Pipe (avoids Queue semaphores).
    
    If already running in a helper process (detected via STREAM_CHECKER_SUBPROCESS_HELPER
    env var), calls subprocess.run() directly to avoid nested spawn timeouts.
    
    On non-macOS: Calls subprocess.run() directly.
    
    Args:
        cmd: Command to run as list of strings
        timeout: Timeout in seconds
        cwd: Working directory (optional)
        env: Environment variables dict (optional)
        text: If True, return stdout/stderr as strings instead of bytes
        stdout_to_file: If True, write child stdout to a temp file and return
            stdout_path and stdout_size instead of stdout bytes (avoids large pipe on macOS).
            Caller must read and delete the file.
        
    Returns:
        Dict with CompletedProcess-like fields:
        - 'returncode': int or None
        - 'stdout': bytes or str (None if stdout_to_file=True)
        - 'stdout_path': str (only if stdout_to_file=True)
        - 'stdout_size': int (only if stdout_to_file=True)
        - 'stderr': bytes or str (depending on text parameter)
        - 'success': bool
        - plus signal/error/timeout fields as before
    """
    stdout_file_path = None
    if stdout_to_file:
        fd, stdout_file_path = tempfile.mkstemp(prefix="stream_checker_stdout_", suffix=".bin")
        os.close(fd)

    def _result_stdout_to_file(path: str, size: int) -> Dict[str, Any]:
        return {
            'stdout': None,
            'stdout_path': path,
            'stdout_size': size,
        }

    # Check if we're already in a helper process (prevents nested spawn)
    if os.environ.get('STREAM_CHECKER_SUBPROCESS_HELPER') == '1':
        # Already in helper process - call subprocess.run() directly
        if stdout_to_file and stdout_file_path:
            try:
                with open(stdout_file_path, 'wb') as fout:
                    process = subprocess.run(
                        cmd,
                        stdout=fout,
                        stderr=subprocess.PIPE,
                        timeout=timeout,
                        cwd=cwd,
                        env=env,
                        text=text
                    )
                size = os.path.getsize(stdout_file_path) if os.path.exists(stdout_file_path) else 0
                signal_info = _classify_returncode(process.returncode)
                return {
                    'returncode': process.returncode,
                    'stderr': process.stderr,
                    'success': True,
                    **_result_stdout_to_file(stdout_file_path, size),
                    **signal_info
                }
            except subprocess.TimeoutExpired as e:
                size = os.path.getsize(stdout_file_path) if os.path.exists(stdout_file_path) else 0
                return {
                    'returncode': None,
                    'stderr': e.stderr if hasattr(e, 'stderr') else None,
                    'success': False,
                    'error': 'timeout',
                    'timeout': timeout,
                    **_result_stdout_to_file(stdout_file_path, size),
                    'signal_num': None,
                    'signal_name': None,
                    'is_signal_kill': False
                }
            except Exception as e:
                return {
                    'returncode': None,
                    'stderr': None,
                    'success': False,
                    'error': str(e),
                    **_result_stdout_to_file(stdout_file_path, 0),
                    'signal_num': None,
                    'signal_name': None,
                    'is_signal_kill': False
                }
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
    
    if platform.system() == "Darwin":
        # macOS: Use multiprocessing spawn to avoid fork crash
        _ensure_spawn_method()
        
        parent_conn = None
        child_conn = None
        process_obj = None

        def _macos_error(**kwargs):
            base = {'stdout': None, 'stderr': None, 'success': False, 'signal_num': None, 'signal_name': None, 'is_signal_kill': False}
            if stdout_to_file and stdout_file_path:
                base['stdout_path'] = stdout_file_path
                base['stdout_size'] = os.path.getsize(stdout_file_path) if os.path.exists(stdout_file_path) else 0
            base.update(kwargs)
            return base

        try:
            # Create Pipe (one-way: parent receives, child sends)
            parent_conn, child_conn = multiprocessing.Pipe(duplex=False)
            
            # Prepare env for child process - merge with current environment and add helper flag
            child_env = dict(os.environ)
            if env:
                child_env.update(env)
            child_env['STREAM_CHECKER_SUBPROCESS_HELPER'] = '1'
            
            if stdout_to_file and stdout_file_path:
                process_obj = multiprocessing.Process(
                    target=_subprocess_worker_stdout_to_file,
                    args=(child_conn, cmd, timeout, cwd, child_env, text, stdout_file_path)
                )
            else:
                process_obj = multiprocessing.Process(
                    target=_subprocess_worker_pipe,
                    args=(child_conn, cmd, timeout, cwd, child_env, text)
                )
            
            process_obj.start()
            child_conn.close()
            
            process_obj.join(timeout=timeout + 5.0)
            
            if process_obj.is_alive():
                process_obj.terminate()
                process_obj.join(timeout=2.0)
                if process_obj.is_alive():
                    process_obj.kill()
                    process_obj.join()
                return _macos_error(error='multiprocessing worker timeout')
            
            exitcode = process_obj.exitcode
            if exitcode is not None and exitcode != 0:
                signal_info = _classify_returncode(exitcode)
                return _macos_error(error=f'multiprocessing worker crashed with exitcode {exitcode}', **signal_info)
            
            try:
                if parent_conn.poll():
                    result = parent_conn.recv()
                    if result:
                        signal_info = _classify_returncode(result.get('returncode'))
                        result.update(signal_info)
                        return result
                return _macos_error(error='no result from multiprocessing worker')
            except Exception as e:
                logger.debug(f"Error receiving from pipe: {e}")
                return _macos_error(error=f'error receiving result: {e}')
        
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
        if stdout_to_file and stdout_file_path:
            try:
                with open(stdout_file_path, 'wb') as fout:
                    process = subprocess.run(
                        cmd,
                        stdout=fout,
                        stderr=subprocess.PIPE,
                        timeout=timeout,
                        cwd=cwd,
                        env=env,
                        text=text
                    )
                size = os.path.getsize(stdout_file_path) if os.path.exists(stdout_file_path) else 0
                signal_info = _classify_returncode(process.returncode)
                return {
                    'returncode': process.returncode,
                    'stderr': process.stderr,
                    'success': True,
                    **_result_stdout_to_file(stdout_file_path, size),
                    **signal_info
                }
            except subprocess.TimeoutExpired as e:
                size = os.path.getsize(stdout_file_path) if os.path.exists(stdout_file_path) else 0
                return {
                    'returncode': None,
                    'stderr': e.stderr if hasattr(e, 'stderr') else None,
                    'success': False,
                    'error': 'timeout',
                    'timeout': timeout,
                    **_result_stdout_to_file(stdout_file_path, size),
                    'signal_num': None,
                    'signal_name': None,
                    'is_signal_kill': False
                }
            except Exception as e:
                return {
                    'returncode': None,
                    'stderr': None,
                    'success': False,
                    'error': str(e),
                    **_result_stdout_to_file(stdout_file_path, 0),
                    'signal_num': None,
                    'signal_name': None,
                    'is_signal_kill': False
                }
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
