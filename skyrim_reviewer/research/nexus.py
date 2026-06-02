"""NexusMods research stage.

Uses the OFFICIAL NexusMods API (https://api.nexusmods.com) — never HTML scraping —
to find and rank the best mods for a category. Respects the API Acceptable Use
Policy: we fetch metadata for ranking, and only download media for mods the user
has recorded as permission-approved in config/permissions.yaml.

Docs: https://app.swaggerhub.com/apis-docs/NexusMods/nexus-mods_public_api_params_in_form_data/1.0
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import channel_config, get_env, load_permissions, require_env
from ..models import MediaAsset, Mod

API_BASE = "https://api.nexusmods.com/v1"
USER_AGENT = "skyrim-reviewer/0.1 (+https://github.com/aifriendly/ai-mod-reviewer)"


class NexusClient:
    """Thin, rate-limit-aware client for the endpoints we need."""

    def __init__(self, api_key: str | None = None, domain: str | None = None):
        self.api_key = api_key or require_env("NEXUS_API_KEY")
        self.domain = domain or channel_config()["channel"]["game_domain"]
        self._client = httpx.Client(
            base_url=API_BASE,
            headers={"apikey": self.api_key, "User-Agent": USER_AGENT,
                     "Accept": "application/json"},
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NexusClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @retry(stop=stop_after_attempt(4),
           wait=wait_exponential(multiplier=2, min=2, max=16))
    def _get(self, path: str) -> Any:
        resp = self._client.get(path)
        # Honour Nexus hourly/daily rate-limit headers politely.
        remaining = resp.headers.get("x-rl-hourly-remaining")
        if remaining is not None and remaining.isdigit() and int(remaining) <= 1:
            time.sleep(2)
        resp.raise_for_status()
        return resp.json()

    # --- discovery endpoints ---
    def trending(self) -> list[dict]:
        return self._get(f"/games/{self.domain}/mods/trending.json")

    def latest_added(self) -> list[dict]:
        return self._get(f"/games/{self.domain}/mods/latest_added.json")

    def latest_updated(self) -> list[dict]:
        return self._get(f"/games/{self.domain}/mods/latest_updated.json")

    def mod_details(self, mod_id: int) -> dict:
        return self._get(f"/games/{self.domain}/mods/{mod_id}.json")


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None


def _to_mod(raw: dict, domain: str) -> Mod:
    mod_id = raw.get("mod_id") or raw.get("uid")
    return Mod(
        mod_id=int(mod_id),
        name=raw.get("name", "") or "",
        summary=(raw.get("summary") or "").strip(),
        author=raw.get("author", "") or "",
        uploaded_by=raw.get("uploaded_by", "") or "",
        category_id=raw.get("category_id"),
        version=str(raw.get("version", "") or ""),
        endorsements=int(raw.get("endorsement_count", 0) or 0),
        downloads=int(raw.get("mod_downloads", 0) or 0),
        updated_at=_parse_ts(raw.get("updated_timestamp") or raw.get("updated_time")),
        page_url=f"https://www.nexusmods.com/{domain}/mods/{mod_id}",
        picture_url=raw.get("picture_url", "") or "",
    )


def _permission_status(mod: Mod, perms: dict) -> bool:
    """True if reuse of this mod's media is permitted (denials always win)."""
    who = mod.uploaded_by or mod.author
    if mod.mod_id in set(perms.get("denied_mod_ids", []) or []):
        return False
    if who in set(perms.get("denied_authors", []) or []):
        return False
    if mod.mod_id in set(perms.get("approved_mod_ids", []) or []):
        return True
    if who in set(perms.get("approved_authors", []) or []):
        return True
    # Informed opt-in "fully automated" mode (see permissions.yaml).
    if perms.get("assume_all_permitted", False):
        return True
    return False


def _score(mod: Mod, weights: dict, now: datetime) -> float:
    # Normalised, weighted ranking. Endorsements & downloads are log-damped so a few
    # mega-mods don't crowd out fresh quality ones.
    import math

    endo = math.log10(mod.endorsements + 1)
    dl = math.log10(mod.downloads + 1)
    recency = 0.0
    if mod.updated_at:
        age_days = max((now - mod.updated_at).days, 0)
        recency = max(0.0, 1.0 - age_days / 365.0)   # 1.0 today -> 0.0 a year old
    has_media = 1.0 if mod.picture_url else 0.0
    return (
        weights.get("weight_endorsements", 0.45) * endo
        + weights.get("weight_downloads_recent", 0.30) * dl
        + weights.get("weight_recency", 0.15) * recency
        + weights.get("weight_has_media", 0.10) * has_media
    )


def research_category(category_id: str, limit: int, client: NexusClient | None = None) -> list[Mod]:
    """Return the top `limit` ranked, eligible mods for a configured category."""
    cfg = channel_config()
    ranking = cfg["ranking"]
    perms = load_permissions()
    domain = cfg["channel"]["game_domain"]

    cat = next((c for c in cfg["categories"] if c["id"] == category_id), None)
    if cat is None:
        raise ValueError(f"Unknown category '{category_id}'. "
                         f"Options: {[c['id'] for c in cfg['categories']]}")
    wanted_cat_ids = set(cat.get("nexus_category_ids", []) or [])

    owns_client = client is None
    client = client or NexusClient(domain=domain)
    now = datetime.now(timezone.utc)
    try:
        # Pool candidates from trending + recently updated, then filter to the category.
        pool: dict[int, dict] = {}
        for raw in (*client.trending(), *client.latest_updated()):
            mid = raw.get("mod_id")
            if mid is not None:
                pool[mid] = raw

        candidates: list[Mod] = []
        for raw in pool.values():
            mod = _to_mod(raw, domain)
            if wanted_cat_ids and mod.category_id not in wanted_cat_ids:
                continue
            if ranking.get("require_media", True) and not mod.picture_url:
                continue
            mod.allow_media_reuse = _permission_status(mod, perms)
            if ranking.get("require_reuse_permission", True) and not mod.allow_media_reuse:
                # Keep it for ranking only if placeholders are allowed; otherwise drop.
                if not perms.get("allow_placeholder_for_unapproved", True):
                    continue
            mod.score = _score(mod, ranking, now)
            candidates.append(mod)

        candidates.sort(key=lambda m: m.score, reverse=True)
        top = candidates[:limit]

        # Enrich the chosen few with full details (one call each) for better narration.
        for mod in top:
            try:
                detail = client.mod_details(mod.mod_id)
                mod.summary = (detail.get("summary") or mod.summary or "").strip()
                mod.endorsements = int(detail.get("endorsement_count", mod.endorsements) or 0)
                if detail.get("picture_url"):
                    mod.picture_url = detail["picture_url"]
            except Exception:
                pass
            if mod.picture_url:
                mod.media.append(MediaAsset(url=mod.picture_url, kind="image"))
        return top
    finally:
        if owns_client:
            client.close()
