"""Hot configuration reload support.

Watches configuration files and reloads them when changed.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """Watches config files for changes and triggers reloads.

    Features:
    - File hash-based change detection
    - Configurable poll interval
    - Callback notification on changes
    - Config validation before applying
    """

    def __init__(
        self,
        config_path: str | Path,
        on_change: Callable[[dict[str, Any]], None] | None = None,
        poll_interval: float = 5.0,
        validator: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        """Initialize config watcher.

        Args:
            config_path: Path to config file
            on_change: Callback when config changes
            poll_interval: Seconds between checks
            validator: Optional function to validate config
        """
        self._config_path = Path(config_path)
        self._on_change = on_change
        self._poll_interval = poll_interval
        self._validator = validator

        self._last_hash: str | None = None
        self._last_config: dict[str, Any] = {}
        self._running = False
        self._task: asyncio.Task | None = None

        # Track reload history
        self._reload_history: list[dict[str, Any]] = []

    @property
    def config_path(self) -> Path:
        """Get config file path."""
        return self._config_path

    @property
    def current_config(self) -> dict[str, Any]:
        """Get current config."""
        return self._last_config.copy()

    @property
    def reload_history(self) -> list[dict[str, Any]]:
        """Get reload history."""
        return list(self._reload_history)

    def _compute_hash(self) -> str | None:
        """Compute hash of config file contents."""
        if not self._config_path.exists():
            return None
        content = self._config_path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def _load_config(self) -> dict[str, Any] | None:
        """Load and parse config file.

        Returns:
            Parsed config or None on error
        """
        if not self._config_path.exists():
            logger.warning(f"Config file not found: {self._config_path}")
            return None

        try:
            with open(self._config_path) as f:
                config = yaml.safe_load(f)
                return config if isinstance(config, dict) else {}
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse config: {e}")
            return None

    def load_initial(self) -> dict[str, Any]:
        """Load initial config.

        Returns:
            Initial config dict

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config is invalid
        """
        if not self._config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self._config_path}")

        config = self._load_config()
        if config is None:
            raise ValueError("Failed to parse config file")

        if self._validator and not self._validator(config):
            raise ValueError("Config validation failed")

        self._last_hash = self._compute_hash()
        self._last_config = config

        self._reload_history.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "action": "initial_load",
            "hash": self._last_hash,
        })

        logger.info(f"Loaded initial config from {self._config_path}")
        return config

    async def _check_for_changes(self) -> bool:
        """Check for config file changes.

        Returns:
            True if config was reloaded
        """
        current_hash = self._compute_hash()

        if current_hash is None:
            return False

        if current_hash == self._last_hash:
            return False

        logger.info("Config file changed, reloading...")

        new_config = self._load_config()
        if new_config is None:
            logger.error("Failed to load new config, keeping previous")
            return False

        # Validate new config
        if self._validator and not self._validator(new_config):
            logger.error("New config validation failed, keeping previous")
            self._reload_history.append({
                "timestamp": datetime.now(UTC).isoformat(),
                "action": "validation_failed",
                "hash": current_hash,
            })
            return False

        # Apply new config
        old_config = self._last_config
        self._last_config = new_config
        self._last_hash = current_hash

        self._reload_history.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "action": "reloaded",
            "hash": current_hash,
            "changes": self._compute_changes(old_config, new_config),
        })

        # Notify callback
        if self._on_change:
            try:
                self._on_change(new_config)
            except Exception as e:
                logger.error(f"Error in config change callback: {e}")

        logger.info("Config reloaded successfully")
        return True

    def _compute_changes(
        self,
        old: dict[str, Any],
        new: dict[str, Any],
        prefix: str = "",
    ) -> list[str]:
        """Compute list of changed keys."""
        changes = []

        all_keys = set(old.keys()) | set(new.keys())
        for key in all_keys:
            full_key = f"{prefix}.{key}" if prefix else key

            if key not in old:
                changes.append(f"+{full_key}")
            elif key not in new:
                changes.append(f"-{full_key}")
            elif old[key] != new[key]:
                if isinstance(old[key], dict) and isinstance(new[key], dict):
                    changes.extend(
                        self._compute_changes(old[key], new[key], full_key)
                    )
                else:
                    changes.append(f"~{full_key}")

        return changes

    async def _watch_loop(self) -> None:
        """Background loop to watch for changes."""
        while self._running:
            try:
                await self._check_for_changes()
            except Exception as e:
                logger.error(f"Error checking config: {e}")

            await asyncio.sleep(self._poll_interval)

    def start(self) -> None:
        """Start watching for config changes."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info(f"Config watcher started: {self._config_path}")

    def stop(self) -> None:
        """Stop watching for config changes."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Config watcher stopped")

    async def force_reload(self) -> bool:
        """Force reload config regardless of changes.

        Returns:
            True if reload successful
        """
        new_config = self._load_config()
        if new_config is None:
            return False

        if self._validator and not self._validator(new_config):
            return False

        old_config = self._last_config
        self._last_config = new_config
        self._last_hash = self._compute_hash()

        self._reload_history.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "action": "force_reload",
            "hash": self._last_hash,
            "changes": self._compute_changes(old_config, new_config),
        })

        if self._on_change:
            self._on_change(new_config)

        return True


class ConfigVersionManager:
    """Manages config versions for rollback support.

    Stores previous config versions for recovery.
    """

    def __init__(self, max_versions: int = 10) -> None:
        """Initialize version manager.

        Args:
            max_versions: Maximum versions to keep
        """
        self._versions: list[dict[str, Any]] = []
        self._max_versions = max_versions

    def save_version(
        self,
        config: dict[str, Any],
        label: str | None = None,
    ) -> int:
        """Save a config version.

        Args:
            config: Config to save
            label: Optional label

        Returns:
            Version number
        """
        version = {
            "version": len(self._versions),
            "timestamp": datetime.now(UTC).isoformat(),
            "label": label,
            "config": config.copy(),
        }

        self._versions.append(version)

        # Trim old versions
        if len(self._versions) > self._max_versions:
            self._versions = self._versions[-self._max_versions :]

        return version["version"]

    def get_version(self, version: int) -> dict[str, Any] | None:
        """Get a specific version.

        Args:
            version: Version number

        Returns:
            Config dict or None
        """
        for v in self._versions:
            if v["version"] == version:
                return v["config"].copy()
        return None

    def get_latest(self) -> dict[str, Any] | None:
        """Get latest version.

        Returns:
            Latest config or None
        """
        if not self._versions:
            return None
        return self._versions[-1]["config"].copy()

    def get_previous(self) -> dict[str, Any] | None:
        """Get previous version.

        Returns:
            Previous config or None
        """
        if len(self._versions) < 2:
            return None
        return self._versions[-2]["config"].copy()

    def list_versions(self) -> list[dict[str, Any]]:
        """List all versions.

        Returns:
            List of version info (without full config)
        """
        return [
            {
                "version": v["version"],
                "timestamp": v["timestamp"],
                "label": v["label"],
            }
            for v in self._versions
        ]
