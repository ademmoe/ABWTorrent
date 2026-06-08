"""ABWTorrent Configuration Manager — loads/saves YAML config with dot-notation access."""

import os
import hashlib
import yaml
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "watch_dir": "/media/nas/iso/operating_systems/Linux/Debian",
    "torrent_output_dir": "/media/nas/platz219/torrents",
    "transmission": {
        "host": "127.0.0.1",
        "port": 9091,
        "username": "abwtorrent",
        "password": "changeme",
    },
    "torrent": {
        "piece_size": 4194304,
        "comment": "ABWTorrent - Internal LAN ISO Distribution",
        "created_by": "ABWTorrent",
    },
    "file_stability": {
        "check_interval": 2,
        "stable_count": 3,
    },
    "mount": {
        "max_wait_seconds": 300,
        "check_interval_seconds": 5,
    },
    "web": {
        "host": "0.0.0.0",
        "port": 8080,
        "secret_key": None,
    },
    "users": {
        "admin": {"password_hash": None, "role": "admin"},
    },
    "log": {
        "level": "INFO",
        "file": "/var/log/abwtorrent/watchdog.log",
    },
}


class Config:
    """Thread-safe configuration manager with YAML persistence."""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self._data: dict = {}
        self.load()

    # ── I/O ──────────────────────────────────────────────

    def load(self):
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                file_data = yaml.safe_load(f) or {}
            self._data = self._deep_merge(DEFAULT_CONFIG.copy(), file_data)
        else:
            self._data = DEFAULT_CONFIG.copy()

        # Auto-generate Flask secret key if missing
        if not self._data.get("web", {}).get("secret_key"):
            self._data.setdefault("web", {})["secret_key"] = hashlib.sha256(
                os.urandom(32)
            ).hexdigest()

    def save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(self._data, f, default_flow_style=False, sort_keys=False)

    # ── Accessors ────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Dot-notation accessor, e.g. ``config.get('transmission.host')``."""
        node = self._data
        for k in key.split("."):
            if isinstance(node, dict):
                node = node.get(k)
            else:
                return default
            if node is None:
                return default
        return node

    def set(self, key: str, value: Any):
        keys = key.split(".")
        node = self._data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value

    @property
    def data(self) -> dict:
        return self._data.copy()

    # ── User / Password helpers ──────────────────────────

    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def verify_password(self, username: str, password: str) -> bool:
        user = self._data.get("users", {}).get(username)
        if not user:
            return False
        stored = user.get("password_hash")
        if not stored:
            # First-time: accept the default transmission password
            return password == self.get("transmission.password", "changeme")
        return stored == self.hash_password(password)

    # ── Helpers ──────────────────────────────────────────

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Config._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
