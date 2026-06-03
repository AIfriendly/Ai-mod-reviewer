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
    cfg = load_yaml("channel.yaml")
    # Multi-game override: `make --game fallout4` sets this so research + footage
    # target another Nexus game without editing config. See config/games.yaml.
    game = os.environ.get("MODREVIEWER_GAME")
    if game:
        cfg.setdefault("channel", {})["game_domain"] = game
        g = games_config().get("games", {}).get(game, {})
        if g.get("accent"):
            cfg.setdefault("branding", {})["accent_color"] = g["accent"]
        if g.get("categories"):          # game-specific category buckets + ids
            cfg["categories"] = g["categories"]
    return cfg


def games_config() -> dict:
    """Registry of supported games (Nexus domain + Steam app id + display name)."""
    try:
        return load_yaml("games.yaml")
    except FileNotFoundError:
        return {}


def voice_config() -> dict:
    return load_yaml("voice.yaml")


def transformations_config() -> dict:
    return load_yaml("transformations.yaml")


def load_permissions() -> dict:
    """Merge the human-edited permissions.yaml with the CLI-managed local file.

    permissions.yaml keeps the documentation/comments; `skyrim-reviewer approve`
    writes to permissions.local.yaml. List fields are unioned; scalar flags in the
    local file override the base.
    """
    base = load_yaml("permissions.yaml")
    local_path = CONFIG_DIR / "permissions.local.yaml"
    if local_path.exists():
        with open(local_path, "r", encoding="utf-8") as fh:
            local = _expand_env(yaml.safe_load(fh) or {})
        for k, v in local.items():
            if isinstance(v, list) and isinstance(base.get(k), list):
                base[k] = list(dict.fromkeys(base[k] + v))
            else:
                base[k] = v
    return base


def add_permission(value: str) -> str:
    """Append an approved author (string) or mod id (int) to permissions.local.yaml.

    Returns the list it was added to ('approved_mod_ids' or 'approved_authors').
    """
    _load_dotenv_once()
    local_path = CONFIG_DIR / "permissions.local.yaml"
    data = {}
    if local_path.exists():
        with open(local_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    key = "approved_mod_ids" if value.isdigit() else "approved_authors"
    item: object = int(value) if value.isdigit() else value
    data.setdefault(key, [])
    if item not in data[key]:
        data[key].append(item)
    with open(local_path, "w", encoding="utf-8") as fh:
        fh.write("# Managed by `skyrim-reviewer approve` — edit permissions.yaml for docs.\n")
        yaml.safe_dump(data, fh, sort_keys=True)
    return key


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
