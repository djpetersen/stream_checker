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
        
        # Merge with defaults to ensure all keys exist
        defaults = self._get_defaults()
        self._config = self._merge_config(defaults, self._config)
        
        # Validate configuration
        self._validate_config()
    
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
    
    def _merge_config(self, defaults: Dict[str, Any], user_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge user config with defaults, recursively"""
        merged = defaults.copy()
        for key, value in user_config.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._merge_config(merged[key], value)
            else:
                merged[key] = value
        return merged
    
    def _validate_config(self):
        """Validate configuration values and fix or warn about invalid values"""
        # Validate security settings
        connection_timeout = self.get("security.connection_timeout")
        if not isinstance(connection_timeout, int) or connection_timeout <= 0:
            logger.warning(f"Invalid connection_timeout: {connection_timeout}, using default: 30")
            self._config.setdefault("security", {})["connection_timeout"] = 30
        
        read_timeout = self.get("security.read_timeout")
        if not isinstance(read_timeout, int) or read_timeout <= 0:
            logger.warning(f"Invalid read_timeout: {read_timeout}, using default: 60")
            self._config.setdefault("security", {})["read_timeout"] = 60
        
        max_url_length = self.get("security.max_url_length")
        if not isinstance(max_url_length, int) or max_url_length <= 0 or max_url_length > 10000:
            logger.warning(f"Invalid max_url_length: {max_url_length}, using default: 2048")
            self._config.setdefault("security", {})["max_url_length"] = 2048
        
        max_urls_per_minute = self.get("security.max_urls_per_minute")
        if not isinstance(max_urls_per_minute, int) or max_urls_per_minute <= 0:
            logger.warning(f"Invalid max_urls_per_minute: {max_urls_per_minute}, using default: 10")
            self._config.setdefault("security", {})["max_urls_per_minute"] = 10
        
        # Validate allowed_schemes
        allowed_schemes = self.get("security.allowed_schemes")
        if not isinstance(allowed_schemes, list) or not all(isinstance(s, str) for s in allowed_schemes):
            logger.warning(f"Invalid allowed_schemes: {allowed_schemes}, using default: ['http', 'https']")
            self._config.setdefault("security", {})["allowed_schemes"] = ["http", "https"]
        
        # Validate resource limits
        max_cpu_time = self.get("resource_limits.max_cpu_time_seconds")
        if not isinstance(max_cpu_time, int) or max_cpu_time <= 0:
            logger.warning(f"Invalid max_cpu_time_seconds: {max_cpu_time}, using default: 300")
            self._config.setdefault("resource_limits", {})["max_cpu_time_seconds"] = 300
        
        max_memory = self.get("resource_limits.max_memory_mb")
        if not isinstance(max_memory, int) or max_memory <= 0:
            logger.warning(f"Invalid max_memory_mb: {max_memory}, using default: 512")
            self._config.setdefault("resource_limits", {})["max_memory_mb"] = 512
        
        max_temp_file_size = self.get("resource_limits.max_temp_file_size_mb")
        if not isinstance(max_temp_file_size, int) or max_temp_file_size <= 0:
            logger.warning(f"Invalid max_temp_file_size_mb: {max_temp_file_size}, using default: 100")
            self._config.setdefault("resource_limits", {})["max_temp_file_size_mb"] = 100
        
        # Validate stream_checker settings
        default_phase = self.get("stream_checker.default_phase")
        if not isinstance(default_phase, int) or default_phase < 1 or default_phase > 4:
            logger.warning(f"Invalid default_phase: {default_phase}, using default: 4")
            self._config.setdefault("stream_checker", {})["default_phase"] = 4
        
        silence_threshold = self.get("stream_checker.default_silence_threshold")
        if not isinstance(silence_threshold, (int, float)) or not (-100 <= silence_threshold <= 0):
            logger.warning(f"Invalid default_silence_threshold: {silence_threshold}, using default: -40")
            self._config.setdefault("stream_checker", {})["default_silence_threshold"] = -40
        
        sample_duration = self.get("stream_checker.default_sample_duration")
        if not isinstance(sample_duration, int) or sample_duration <= 0 or sample_duration > 300:
            logger.warning(f"Invalid default_sample_duration: {sample_duration}, using default: 10")
            self._config.setdefault("stream_checker", {})["default_sample_duration"] = 10
        
        # Validate logging settings
        log_level = self.get("logging.level")
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if not isinstance(log_level, str) or log_level.upper() not in valid_levels:
            logger.warning(f"Invalid logging.level: {log_level}, using default: INFO")
            self._config.setdefault("logging", {})["level"] = "INFO"
        else:
            # Normalize to uppercase
            self._config.setdefault("logging", {})["level"] = log_level.upper()
        
        max_file_size = self.get("logging.max_file_size_mb")
        if not isinstance(max_file_size, int) or max_file_size <= 0:
            logger.warning(f"Invalid max_file_size_mb: {max_file_size}, using default: 10")
            self._config.setdefault("logging", {})["max_file_size_mb"] = 10
        
        backup_count = self.get("logging.backup_count")
        if not isinstance(backup_count, int) or backup_count < 0:
            logger.warning(f"Invalid backup_count: {backup_count}, using default: 5")
            self._config.setdefault("logging", {})["backup_count"] = 5
        
        # Validate database settings
        backup_retention = self.get("database.backup_retention_days")
        if not isinstance(backup_retention, int) or backup_retention < 0:
            logger.warning(f"Invalid backup_retention_days: {backup_retention}, using default: 30")
            self._config.setdefault("database", {})["backup_retention_days"] = 30
