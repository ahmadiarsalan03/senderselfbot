"""Configuration loading utilities for the self management bot."""
from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class ConfigError(RuntimeError):
    """Raised when the configuration file is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """Container for application wide configuration values."""

    api_id: int
    api_hash: str
    encryption_key: str
    storage_dir: Path
    sessions_dir: Path
    extracts_dir: Path

    @classmethod
    def from_parser(cls, parser: configparser.ConfigParser, *, base_path: Path) -> "Config":
        try:
            api_id = parser.getint("telegram", "api_id")
            api_hash = parser.get("telegram", "api_hash")
        except (configparser.NoSectionError, configparser.NoOptionError) as exc:
            raise ConfigError("Configuration file is missing required [telegram] section") from exc

        try:
            encryption_key = parser.get("security", "encryption_key")
        except (configparser.NoSectionError, configparser.NoOptionError) as exc:
            raise ConfigError("Configuration file is missing required [security] section") from exc

        storage_root = parser.get("storage", "root", fallback="data")
        storage_dir = (base_path / storage_root).resolve()
        sessions_dir = (storage_dir / "sessions").resolve()
        extracts_dir = (storage_dir / "extracts").resolve()

        return cls(
            api_id=api_id,
            api_hash=api_hash,
            encryption_key=encryption_key,
            storage_dir=storage_dir,
            sessions_dir=sessions_dir,
            extracts_dir=extracts_dir,
        )


def load_config(path: Optional[os.PathLike[str] | str] = None) -> Config:
    """Load configuration from the given path or default location.

    Parameters
    ----------
    path:
        Optional configuration file path. When omitted the function looks for a
        ``config.ini`` file next to the project root.
    """

    if path is None:
        path = Path("config.ini")
    else:
        path = Path(path)

    if not path.exists():
        raise ConfigError(f"Configuration file {path} does not exist")

    parser = configparser.ConfigParser()
    parser.read(path)
    config = Config.from_parser(parser, base_path=path.parent)
    _ensure_directories(config)
    return config


def _ensure_directories(config: Config) -> None:
    """Create required directories if they do not yet exist."""

    config.storage_dir.mkdir(parents=True, exist_ok=True)
    config.sessions_dir.mkdir(parents=True, exist_ok=True)
    config.extracts_dir.mkdir(parents=True, exist_ok=True)
