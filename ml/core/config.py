"""Load YAML configuration files from the repository ``config/`` directory.

The directory is resolved from ``EWAI_CONFIG_DIR`` when set, otherwise relative to the repository root.
Thresholds and scientific constants live in YAML (never hard-coded in algorithms) so they can be
documented, reviewed and changed without touching code.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def config_dir() -> Path:
    """Return the configuration directory."""
    env = os.environ.get("EWAI_CONFIG_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "config"


@lru_cache(maxsize=32)
def _load(path_str: str) -> dict[str, Any]:
    with open(path_str, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path_str} must contain a mapping at top level")
    return data


def load_config(name: str) -> dict[str, Any]:
    """Load ``config/<name>.yaml`` and return the parsed mapping (cached)."""
    path = config_dir() / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path.name}")
    return _load(str(path))
