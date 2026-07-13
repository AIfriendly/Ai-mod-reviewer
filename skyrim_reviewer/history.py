"""Video history ledger — enforces two channel rules:

  1. Never make the same video twice: mods already featured are excluded from future
     automated selections (per game).
  2. Always feature what's trending now: the research stage prioritises currently
     trending mods (the trending boost lives in research/nexus.py scoring).

The ledger is a small JSON file at the repo root. Commit it so the "no repeats" rule
persists across machines / ephemeral runs.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

HISTORY_PATH = Path(__file__).resolve().parent.parent / "history.json"


def _load() -> dict:
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save(data: dict) -> None:
    HISTORY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _game_of(project) -> str:
    try:
        from .config import channel_config
        return channel_config()["channel"]["game_domain"]
    except Exception:
        return "unknown"


def seen_mod_ids(game: str) -> set[int]:
    """Mod ids already featured in a video for this game."""
    data = _load()
    ids: set[int] = set()
    for entry in data.get(game, []):
        ids.update(int(m) for m in entry.get("mod_ids", []))
    return ids


def seen_titles(game: str) -> list[str]:
    return [e.get("title", "") for e in _load().get(game, [])]


def mods_featured_elsewhere(game: str, slug: str) -> dict[int, str]:
    """Map {mod_id -> the slug of a DIFFERENT video that already featured it}.

    Used to catch a new spec that re-uses a previously-showcased mod. Entries for the
    same slug are ignored so re-rendering an existing video doesn't false-alarm."""
    out: dict[int, str] = {}
    for entry in _load().get(game, []):
        if entry.get("slug") == slug:
            continue
        for mid in entry.get("mod_ids", []):
            out.setdefault(int(mid), entry.get("slug", "?"))
    return out


def record_video(project) -> None:
    """Record a produced video's mods + title so it's never repeated."""
    game = _game_of(project)
    data = _load()
    data.setdefault(game, []).append({
        "date": date.today().isoformat(),
        "slug": project.slug,
        "title": project.script.title if project.script else "",
        "category": getattr(project, "category_id", ""),
        "mod_ids": [m.mod_id for m in project.mods],
    })
    _save(data)
