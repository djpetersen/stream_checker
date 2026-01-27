"""Utility functions for multiprocessing operations"""

import multiprocessing
import platform
import logging
from typing import Optional, Tuple, Any, Callable
import queue as queue_module

from stream_checker.utils.subprocess_utils import run_subprocess_safe

logger = logging.getLogger("stream_checker")

# Multiprocessing timeout constants
# These constants ensure consistent timeout behavior across all multiprocessing operations
DEFAULT_QUEUE_GET_TIMEOUT = 0.5  # Default timeout for queue.get() operations (seconds)
DEFAULT_PROCESS_CLEANUP_TIMEOUT = 2.0  # Default timeout for process cleanup operations (seconds)
QUEUE_DRAIN_TIMEOUT = 0.1  # Timeout for draining queue items during cleanup (seconds)
QUEUE_JOIN_THREAD_TIMEOUT = 2.0  # Timeout for queue.join_thread() during cleanup (seconds)

# Use spawn method on macOS to avoid fork issues
# Defer setting until actually needed to avoid conflicts in Flask/multi-threaded environments
_mp_start_method_set = False


def ensure_spawn_method():
    """
    Ensure multiprocessing start method is configured correctly for the platform.
    
    Platform-specific behavior:
    - macOS: Enforces 'spawn' method (required to avoid fork-related crashes)
    - Linux/Raspberry Pi: Does not force spawn globally; uses default (usually 'fork')
      The helper works correctly under both 'fork' and 'spawn' methods.
    
    This function is safe to call multiple times and handles cases where the start
    method is already set (e.g., by another module or the main process).
    
    Note: On Linux, 'fork' is the default and generally safe. The helper function
    `run_process_with_queue()` works correctly regardless of the start method.
    """
    global _mp_start_method_set
    if _mp_start_method_set:
        return
    
    if not hasattr(multiprocessing, 'get_start_method'):
        # Older Python versions - nothing to do
        _mp_start_method_set = True
        return
    
    system = platform.system()
    
    try:
        current_method = multiprocessing.get_start_method(allow_none=True)
        
        if system == "Darwin":
            # macOS: Enforce 'spawn' method to avoid fork-related crashes
            if current_method is None:
                # Not set yet, set it to spawn
                try:
                    multiprocessing.set_start_method('spawn')
                    _mp_start_method_set = True
                except RuntimeError:
                    # Can't set - might already be set in another process
                    # This is safe - if it's already set, we're good
                    _mp_start_method_set = True
            elif current_method == 'spawn':
                # Already set to spawn - perfect
                _mp_start_method_set = True
            else:
                # Try to change it to spawn, but don't force if it fails
                try:
                    multiprocessing.set_start_method('spawn', force=True)
                    _mp_start_method_set = True
                except RuntimeError:
                    # Already set or can't change - this is OK
                    # The helper will work, but may have fork issues on macOS
                    _mp_start_method_set = True
        else:
            # Linux/Other platforms: Don't force spawn globally
            # Default is usually 'fork' which is safe on Linux
            # The helper works correctly under both 'fork' and 'spawn'
            if current_method is None:
                # Not set - use default (usually 'fork' on Linux)
                # Don't set it explicitly - let the system use its default
                _mp_start_method_set = True
            else:
                # Already set - respect the existing setting
                # Could be 'fork', 'spawn', or 'forkserver' - all are fine
                _mp_start_method_set = True
    except RuntimeError:
        # Start method already set or can't be changed - this is OK
        # Safe to mark as set since we can't do anything about it
        _mp_start_method_set = True
    except Exception as e:
        # Unexpected error - log but don't fail
        logger.debug(f"Unexpected error in ensure_spawn_method: {e}")
        _mp_start_method_set = True


def cleanup_multiprocessing_queue(queue: Optional[multiprocessing.Queue], context: str = "unknown") -> None:
    """
    Safely cleanup multiprocessing queue to prevent semaphore leaks.
    
    This function properly drains and closes a multiprocessing queue,
    which is critical for preventing semaphore leaks on macOS.
    
    Args:
        queue: The multiprocessing.Queue to cleanup, or None
        context: Context string for logging (e.g., function name)
    
    Note:
        This should be called in finally blocks after using a queue.
        The queue should not be used after calling this function.
    """
    if queue is None:
        return
    
    try:
        # CRITICAL: Properly drain and close queue to prevent semaphore leaks
        try:
            # Get any remaining items (with timeout to avoid blocking)
            import queue as queue_module
            while True:
                try:
                    queue.get(timeout=QUEUE_DRAIN_TIMEOUT)
                except queue_module.Empty:
                    break
                except Exception as e:
                    logger.debug(f"Error draining queue in {context}: {e}")
                    break
        except Exception as e:
            logger.debug(f"Error in queue drain loop in {context}: {e}")
        
        try:
            queue.close()
        except Exception as e:
            logger.debug(f"Error closing queue in {context}: {e}")
        
        try:
            queue.join_thread(timeout=QUEUE_JOIN_THREAD_TIMEOUT)
        except Exception as e:
            logger.debug(f"Error joining queue thread in {context}: {e}")
    except Exception as e:
        logger.debug(f"Error in queue cleanup in {context}: {e}")


def cleanup_multiprocessing_process(
    process: Optional[multiprocessing.Process],
    context: str = "unknown",
    timeout: float = DEFAULT_PROCESS_CLEANUP_TIMEOUT
) -> None:
    """
    Safely cleanup multiprocessing process.
    
    Args:
        process: The multiprocessing.Process to cleanup, or None
        context: Context string for logging (e.g., function name)
        timeout: Timeout in seconds for join operations
    """
    if process is None:
        return
    
    try:
        # Check if process was ever started (has is_alive method)
        if not hasattr(process, 'is_alive'):
            return
        
        if process.is_alive():
            process.terminate()
            process.join(timeout=timeout)
            if process.is_alive():
                process.kill()
                process.join()
    except Exception as e:
        logger.debug(f"Error cleaning up process in {context}: {e}")


def run_process_with_queue(
    target: Callable,
    args: tuple,
    *,
    join_timeout: float,
    get_timeout: float = DEFAULT_QUEUE_GET_TIMEOUT,
    name: Optional[str] = None
) -> Tuple[bool, Optional[dict]]:
    """
    Run a worker function in a separate process and get result via queue.
    
    This helper centralizes the process creation, queue management, and cleanup
    to ensure consistent behavior across all multiprocessing sites.
    
    Args:
        target: Worker function to run (must accept queue as first arg)
        args: Arguments tuple for target (queue will be prepended automatically)
        join_timeout: Timeout in seconds for process.join()
        get_timeout: Timeout in seconds for queue.get() (default: 0.5)
        name: Optional context name for logging (default: target function name)
    
    Returns:
        Tuple of (success: bool, result: Optional[dict]):
        - (True, result_dict) if process completed and result was retrieved
        - (False, None) if process timed out, crashed, or queue was empty
    
    Note:
        The target function must accept a multiprocessing.Queue as its first argument
        and call queue.put(result_dict) with the result.
    """
    context = name or getattr(target, '__name__', 'unknown')
    mp_queue = None
    process_obj = None
    
    try:
        # Ensure spawn method is set before creating queue
        ensure_spawn_method()
        
        # Create queue and process
        mp_queue = multiprocessing.Queue()
        process_obj = multiprocessing.Process(
            target=target,
            args=(mp_queue,) + args
        )
        
        # Start process
        process_obj.start()
        
        # Wait for process with timeout
        process_obj.join(timeout=join_timeout)
        
        # Check if process timed out
        if process_obj.is_alive():
            # Process timed out - will be cleaned up in finally block
            return (False, None)
        
        # Check process exit code for signals or errors
        exitcode = process_obj.exitcode
        if exitcode is not None and exitcode != 0:
            # Process exited with non-zero code - could be signal (negative) or error
            failure_info = {
                'exitcode': exitcode,
                'signal': None,
                'signal_name': None,
                'stdout': None,
                'stderr': None
            }
            
            # Check if exitcode is negative (signal)
            if exitcode < 0:
                signal_num = -exitcode
                failure_info['signal'] = signal_num
                # Map common signals to names
                signal_names = {
                    11: 'SIGSEGV',
                    9: 'SIGKILL',
                    15: 'SIGTERM',
                    2: 'SIGINT',
                    3: 'SIGQUIT'
                }
                failure_info['signal_name'] = signal_names.get(signal_num, f'SIG{signal_num}')
            
            # Try to get result from queue to capture stdout/stderr if available
            try:
                result = mp_queue.get(timeout=get_timeout)
                if result:
                    failure_info['stdout'] = result.get('stdout')
                    failure_info['stderr'] = result.get('stderr')
            except queue_module.Empty:
                pass
            
            return (False, failure_info)
        
        # Get result from queue if available (use timeout to avoid race condition)
        try:
            result = mp_queue.get(timeout=get_timeout)
            if result and result.get('returncode') is not None and result.get('returncode') != 0:
                # Worker returned non-zero returncode - treat as failure
                failure_info = {
                    'exitcode': result.get('returncode'),
                    'signal': None,
                    'signal_name': None,
                    'stdout': result.get('stdout'),
                    'stderr': result.get('stderr')
                }
                # Check if returncode is negative (signal)
                if failure_info['exitcode'] < 0:
                    signal_num = -failure_info['exitcode']
                    failure_info['signal'] = signal_num
                    signal_names = {
                        11: 'SIGSEGV',
                        9: 'SIGKILL',
                        15: 'SIGTERM',
                        2: 'SIGINT',
                        3: 'SIGQUIT'
                    }
                    failure_info['signal_name'] = signal_names.get(signal_num, f'SIG{signal_num}')
                return (False, failure_info)
            return (True, result)
        except queue_module.Empty:
            # Queue is empty - process may have crashed or timed out
            return (False, None)
    
    except Exception as e:
        logger.debug(f"Error in run_process_with_queue ({context}): {e}")
        return (False, None)
    
    finally:
        # Clean up resources - CRITICAL to prevent semaphore leaks
        # This handles both normal completion and timeout cases
        cleanup_multiprocessing_process(process_obj, context=context, timeout=DEFAULT_PROCESS_CLEANUP_TIMEOUT)
        cleanup_multiprocessing_queue(mp_queue, context=context)


def _run_subprocess_worker_pipe(conn, cmd, timeout):
    """Worker function for multiprocessing using Pipe - must be at module level for pickling.
    Routes through run_subprocess_safe for improved stability on macOS.
    """
    # Route through run_subprocess_safe for improved stability on macOS
    result = run_subprocess_safe(
        cmd,
        timeout=timeout,
        text=False
    )
    # Return in the same format as before for compatibility
    result_dict = {
        'success': result.get('success', False),
        'returncode': result.get('returncode'),
        'stdout': result.get('stdout'),
        'stderr': result.get('stderr')
    }
    # Include error if present
    if result.get('error'):
        result_dict['error'] = result.get('error')
    
    # Send result through pipe
    try:
        conn.send(result_dict)
    except Exception:
        pass
    finally:
        conn.close()


def run_process_with_pipe(
    target: Callable,
    args: tuple,
    *,
    join_timeout: float,
    name: Optional[str] = None
) -> Tuple[bool, Optional[dict]]:
    """
    Run a worker function in a separate process and get result via Pipe (avoids Queue semaphores).
    
    This helper uses Pipe instead of Queue to avoid semaphore-backed IPC on macOS spawn.
    
    Args:
        target: Worker function to run (must accept conn as first arg)
        args: Arguments tuple for target (conn will be prepended automatically)
        join_timeout: Timeout in seconds for process.join()
        name: Optional context name for logging (default: target function name)
    
    Returns:
        Tuple of (success: bool, result: Optional[dict]):
        - (True, result_dict) if process completed and result was retrieved
        - (False, failure_info) if process crashed with signal or error
        - (False, None) if process timed out
    """
    context = name or getattr(target, '__name__', 'unknown')
    parent_conn = None
    child_conn = None
    process_obj = None
    
    try:
        # Ensure spawn method is set
        ensure_spawn_method()
        
        # Create Pipe (one-way: parent receives, child sends)
        parent_conn, child_conn = multiprocessing.Pipe(duplex=False)
        
        # Create process
        process_obj = multiprocessing.Process(
            target=target,
            args=(child_conn,) + args
        )
        
        # Start process
        process_obj.start()
        # Close child end in parent process
        child_conn.close()
        
        # Wait for process with timeout
        process_obj.join(timeout=join_timeout)
        
        # Check if process timed out
        if process_obj.is_alive():
            # Process timed out - will be cleaned up in finally block
            return (False, None)
        
        # Check process exit code for signals or errors
        exitcode = process_obj.exitcode
        if exitcode is not None and exitcode != 0:
            # Process exited with non-zero code - could be signal (negative) or error
            failure_info = {
                'exitcode': exitcode,
                'signal': None,
                'signal_name': None,
                'stdout': None,
                'stderr': None
            }
            
            # Check if exitcode is negative (signal)
            if exitcode < 0:
                signal_num = -exitcode
                failure_info['signal'] = signal_num
                # Map common signals to names
                signal_names = {
                    11: 'SIGSEGV',
                    9: 'SIGKILL',
                    15: 'SIGTERM',
                    2: 'SIGINT',
                    3: 'SIGQUIT'
                }
                failure_info['signal_name'] = signal_names.get(signal_num, f'SIG{signal_num}')
            
            # Try to get result from pipe if available
            try:
                if parent_conn.poll():
                    result = parent_conn.recv()
                    if result:
                        failure_info['stdout'] = result.get('stdout')
                        failure_info['stderr'] = result.get('stderr')
            except Exception:
                pass
            
            return (False, failure_info)
        
        # Get result from pipe
        try:
            if parent_conn.poll():
                result = parent_conn.recv()
                if result and result.get('returncode') is not None and result.get('returncode') != 0:
                    # Worker returned non-zero returncode - treat as failure
                    failure_info = {
                        'exitcode': result.get('returncode'),
                        'signal': None,
                        'signal_name': None,
                        'stdout': result.get('stdout'),
                        'stderr': result.get('stderr')
                    }
                    # Check if returncode is negative (signal)
                    if failure_info['exitcode'] < 0:
                        signal_num = -failure_info['exitcode']
                        failure_info['signal'] = signal_num
                        signal_names = {
                            11: 'SIGSEGV',
                            9: 'SIGKILL',
                            15: 'SIGTERM',
                            2: 'SIGINT',
                            3: 'SIGQUIT'
                        }
                        failure_info['signal_name'] = signal_names.get(signal_num, f'SIG{signal_num}')
                    return (False, failure_info)
                return (True, result)
            else:
                # No data in pipe - process may have crashed
                return (False, None)
        except Exception as e:
            logger.debug(f"Error receiving from pipe in {context}: {e}")
            return (False, None)
    
    except Exception as e:
        logger.debug(f"Error in run_process_with_pipe ({context}): {e}")
        return (False, None)
    
    finally:
        # Clean up resources
        if parent_conn:
            try:
                parent_conn.close()
            except Exception:
                pass
        cleanup_multiprocessing_process(process_obj, context=context, timeout=DEFAULT_PROCESS_CLEANUP_TIMEOUT)
