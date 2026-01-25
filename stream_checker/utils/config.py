"""Configuration management"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("stream_checker")


def expand_path(path: str) -> str:
    """Expand user home directory and environment variables in path"""
    return os.path.expanduser(os.path.expandvars(path))


class Config:
    """Configuration manager"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._find_config_file()
        self._config: Dict[str, Any] = {}
        self.load()
    
    def _find_config_file(self) -> str:
        """Find config file in standard locations"""
        # Check current directory
        if os.path.exists("config.yaml"):
            return "config.yaml"
        # Check user home directory
        home_config = expand_path("~/.stream_checker/config.yaml")
        if os.path.exists(home_config):
            return home_config
        # Return default location
        return "config.yaml"
    
    def load(self):
        """Load configuration from file"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f) or {}
            except (yaml.YAMLError, IOError, OSError) as e:
                logger.warning(f"Error loading config file {self.config_path}: {e}. Using defaults.")
                self._config = self._get_defaults()
        else:
            # Use defaults
            self._config = self._get_defaults()
    
    def _get_defaults(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "database": {
                "path": "~/.stream_checker/stream_checker.db",
                "backup_enabled": True,
                "backup_retention_days": 30
            },
            "storage": {
                "results_dir": "~/.stream_checker/results",
                "temp_dir": "/tmp/stream_checker",
                "cleanup_after_test": True,
                "max_temp_file_size_mb": 100
            },
            "security": {
                "allowed_schemes": ["http", "https"],
                "block_private_ips": False,
                "connection_timeout": 30,
                "read_timeout": 60,
                "max_url_length": 2048,
                "max_urls_per_minute": 10
            },
            "resource_limits": {
                "max_cpu_time_seconds": 300,
                "max_memory_mb": 512,
                "max_temp_file_size_mb": 100
            },
            "logging": {
                "level": "INFO",
                "file": "~/.stream_checker/logs/stream_checker.log",
                "max_file_size_mb": 10,
                "backup_count": 5
            },
            "stream_checker": {
                "default_phase": 4,
                "default_silence_threshold": -40,
                "default_sample_duration": 10
            }
        }
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'database.path')"""
        keys = key_path.split('.')
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def get_path(self, key_path: str, default: Any = None) -> str:
        """Get configuration path and expand user directory"""
        path = self.get(key_path, default)
        if path:
            return expand_path(path)
        return path
