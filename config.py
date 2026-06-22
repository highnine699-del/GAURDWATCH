"""
Configuration Management for GuardWatch
Loads and validates configuration from config.json
"""
import json
import os
from pathlib import Path
from typing import Any, Dict


class Config:
    """Configuration manager for GuardWatch"""
    
    def __init__(self, config_path: Path = None):
        self.config_path = config_path or Path(__file__).parent / "config.json"
        self._config: Dict[str, Any] = {}
        self.load()
    
    def load(self) -> None:
        """Load configuration from JSON file"""
        if not self.config_path.exists():
            self._create_default_config()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
            self._validate()
        except Exception as e:
            raise RuntimeError(f"Failed to load config: {e}")
    
    def _create_default_config(self) -> None:
        """Create default configuration file"""
        default_config = {
            "modules": {
                "idle_wake": True,
                "webcam": True,
                "screenshots": True,
                "clipboard": True,
                "keystrokes": True,
                "steps": True,
                "browser_history": True,
                "window_titles": True,
                "usb_detection": True,
                "failed_logins": True,
                "file_activity": True
            },
            "intervals": {
                "screenshot_min": 90,
                "screenshot_max": 240,
                "idle_trigger_sec": 300,
                "clipboard_poll_sec": 1.5,
                "window_poll_sec": 3,
                "usb_poll_sec": 2,
                "webcam_warmup_frames": 5,
                "step_min_gap_sec": 0.6,
                "health_check_sec": 30
            },
            "dashboard": {
                "enabled": True,
                "port": 5555,
                "host": "0.0.0.0",
                "refresh_interval_sec": 2,
                "require_auth": False,
                "username": "",
                "password": ""
            },
            "storage": {
                "evidence_root": "APPDATA/Microsoft/CLR/gw_evidence",
                "use_sqlite": True,
                "database_name": "evidence.db",
                "screenshot_format": "png",
                "screenshot_quality": 90,
                "encrypt_sensitive": False,
                "verify_integrity": True
            },
            "retention": {
                "enabled": True,
                "retain_days": 30,
                "compress_old": True,
                "max_size_gb": 50
            },
            "monitoring": {
                "monitored_dirs": [
                    "Documents",
                    "Downloads",
                    "Desktop",
                    "LOCALAPPDATA/Temp",
                    "APPDATA/Microsoft/Office"
                ],
                "suspicious_extensions": [".exe", ".bat", ".cmd", ".ps1", ".dll", ".scr", ".vbs", ".js"],
                "ignore_dirs": [".git", "__pycache__", "node_modules", "AppData", "$RECYCLE.BIN"]
            },
            "risk_engine": {
                "enabled": True,
                "correlation_window_sec": 300,
                "high_priority_threshold": 3,
                "critical_threshold": 5
            },
            "recovery": {
                "enabled": True,
                "max_retries": 3,
                "retry_delay_sec": 10
            },
            "logging": {
                "structured": True,
                "console": True,
                "level": "INFO"
            }
        }
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2)
        
        self._config = default_config
    
    def _validate(self) -> None:
        """Validate configuration values"""
        required_sections = ["modules", "intervals", "dashboard", "storage", "retention"]
        for section in required_sections:
            if section not in self._config:
                raise ValueError(f"Missing required config section: {section}")
    
    def get(self, *keys, default: Any = None) -> Any:
        """Get configuration value by nested keys"""
        value = self._config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value
    
    def set(self, *keys, value: Any) -> None:
        """Set configuration value by nested keys"""
        config = self._config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        config[keys[-1]] = value
        self.save()
    
    def save(self) -> None:
        """Save configuration to file"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, indent=2)
    
    @property
    def modules(self) -> Dict[str, bool]:
        return self._config.get("modules", {})
    
    @property
    def intervals(self) -> Dict[str, int]:
        return self._config.get("intervals", {})
    
    @property
    def dashboard(self) -> Dict[str, Any]:
        return self._config.get("dashboard", {})
    
    @property
    def storage(self) -> Dict[str, Any]:
        return self._config.get("storage", {})
    
    @property
    def retention(self) -> Dict[str, Any]:
        return self._config.get("retention", {})
    
    @property
    def monitoring(self) -> Dict[str, Any]:
        return self._config.get("monitoring", {})
    
    @property
    def risk_engine(self) -> Dict[str, Any]:
        return self._config.get("risk_engine", {})
    
    @property
    def recovery(self) -> Dict[str, Any]:
        return self._config.get("recovery", {})
    
    @property
    def logging(self) -> Dict[str, Any]:
        return self._config.get("logging", {})
    
    def get_evidence_root(self) -> Path:
        """Get evidence root path with environment variable expansion"""
        root_str = self.storage.get("evidence_root", "APPDATA/Microsoft/CLR/gw_evidence")
        root_str = root_str.replace("APPDATA", os.environ.get("APPDATA", Path.home()))
        root_str = root_str.replace("LOCALAPPDATA", os.environ.get("LOCALAPPDATA", ""))
        return Path(root_str)
    
    def get_monitored_dirs(self) -> list[Path]:
        """Get list of monitored directories with environment variable expansion"""
        dirs = []
        for dir_str in self.monitoring.get("monitored_dirs", []):
            dir_str = dir_str.replace("APPDATA", os.environ.get("APPDATA", ""))
            dir_str = dir_str.replace("LOCALAPPDATA", os.environ.get("LOCALAPPDATA", ""))
            dir_path = Path(dir_str)
            if not dir_path.is_absolute():
                dir_path = Path.home() / dir_str
            dirs.append(dir_path)
        return dirs


# Global config instance
config = Config()
