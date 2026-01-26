"""Utility functions for file operations"""

import os
import logging
from typing import Optional

logger = logging.getLogger("stream_checker")


def safe_remove_file(file_path: Optional[str], context: str = "unknown") -> bool:
    """
    Safely remove a file, logging any errors.
    
    Args:
        file_path: Path to file to remove, or None
        context: Context string for logging (e.g., function name)
    
    Returns:
        True if file was removed or didn't exist, False on error
    """
    if not file_path:
        return True
    
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            return True
        return True  # File doesn't exist, which is fine
    except (OSError, PermissionError) as e:
        logger.debug(f"Could not delete temp file {file_path} in {context}: {e}")
        return False
    except Exception as e:
        logger.debug(f"Unexpected error deleting file {file_path} in {context}: {e}")
        return False
