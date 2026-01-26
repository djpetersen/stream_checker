"""Utility functions for multiprocessing operations"""

import multiprocessing
import logging
from typing import Optional

logger = logging.getLogger("stream_checker")


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
                    queue.get(timeout=0.1)
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
            queue.join_thread(timeout=2)
        except Exception as e:
            logger.debug(f"Error joining queue thread in {context}: {e}")
    except Exception as e:
        logger.debug(f"Error in queue cleanup in {context}: {e}")


def cleanup_multiprocessing_process(
    process: Optional[multiprocessing.Process],
    context: str = "unknown",
    timeout: float = 1.0
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
        if process.is_alive():
            process.terminate()
            process.join(timeout=timeout)
            if process.is_alive():
                process.kill()
                process.join()
    except Exception as e:
        logger.debug(f"Error cleaning up process in {context}: {e}")
