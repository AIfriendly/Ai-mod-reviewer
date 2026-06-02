"""Load and resolve configuration from config/*.yaml + environment (.env).

`${ENV_VAR}` placeholders inside the YAML are expanded from the environment.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .models import VideoProfile

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"

_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand_env(obj: Any) -> Any:
    """Recursively replace ${VAR} with os.environ value (empty string if unset)."""
    if isinstance(obj, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), obj)
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(v) for v in obj]
    return obj


@lru_cache(maxsize=1)
def _load_dotenv_once() -> None:
    load_dotenv(ROOT / ".env")


def load_yaml(name: str) -> dict:
    _load_dotenv_once()
    path = CONFIG_DIR / name
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return _expand_env(data)


def channel_config() -> dict:
    return load_yaml("channel.yaml")


def voice_config() -> dict:
    return load_yaml("voice.yaml")


def active_profile(cfg: dict | None = None, override: str | None = None) -> tuple[str, VideoProfile]:
    """Return (profile_name, VideoProfile) honouring an optional CLI override."""
    cfg = cfg or channel_config()
    video = cfg["video"]
    name = override or video.get("active_profile", "test")
    profiles = video["profiles"]
    if name not in profiles:
        raise ValueError(f"Unknown profile '{name}'. Options: {list(profiles)}")
    return name, VideoProfile(**profiles[name])


def require_env(key: str) -> str:
    _load_dotenv_once()
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(
            f"Missing required environment variable {key}. "
            f"Copy .env.example to .env and fill it in."
        )
    return val


def get_env(key: str, default: str = "") -> str:
    _load_dotenv_once()
    return os.environ.get(key, default)
