"""
Centralized YAML Configuration Loader for Translation Studio.

Loads and validates config files from the /config directory and exposes
them as typed dictionaries. All modules should source their config values
through this loader instead of hardcoding defaults.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml


def load_env() -> None:
    """Load environment variables from .env file if not already set."""
    # 1. Try python-dotenv if installed
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
        return
    except ImportError:
        pass

    # 2. Pure Python fallback parser for .env
    candidates = [
        Path(__file__).resolve().parents[2] / ".env",
        Path.cwd() / ".env",
    ]
    for env_path in candidates:
        if env_path.is_file():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
            break


# Ensure .env is loaded whenever config_loader is imported
load_env()

CONFIG_DIR = Path(os.getenv("CONFIG_DIR", Path(__file__).resolve().parents[2] / "config"))



def _load_yaml(filename: str) -> Dict[str, Any]:
    """Read and parse a YAML file from the config directory."""
    path = CONFIG_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=None)
def get_prompts_config() -> Dict[str, Any]:
    """Return the parsed contents of config/prompts.yaml."""
    return _load_yaml("prompts.yaml")


@lru_cache(maxsize=None)
def get_limits_config() -> Dict[str, Any]:
    """Return the parsed contents of config/limits.yaml."""
    return _load_yaml("limits.yaml")


@lru_cache(maxsize=None)
def get_routing_config() -> Dict[str, Any]:
    """Return the parsed contents of config/routing.yaml."""
    return _load_yaml("routing.yaml")


@lru_cache(maxsize=None)
def get_languages_config() -> Dict[str, Any]:
    """Return the parsed contents of config/languages.yaml."""
    return _load_yaml("languages.yaml")


@lru_cache(maxsize=None)
def get_fonts_config() -> Dict[str, Any]:
    """Return the parsed contents of config/fonts.yaml."""
    return _load_yaml("fonts.yaml")
