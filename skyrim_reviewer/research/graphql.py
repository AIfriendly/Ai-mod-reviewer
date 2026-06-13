"""Full-catalog mod discovery via the NexusMods v2 GraphQL API.

The v1 REST API has no search and only exposes trending / recently-updated lists, so
category research runs dry fast. The v2 GraphQL `mods` query searches the WHOLE
catalogue by category, sorted by endorsements — the same backend the website uses.
This is how we surface the best mods for any bucket, not just freshly-updated ones.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..config import channel_config, require_env
from ..models import Mod

_V2 = "https://api.nexusmods.com/v2/graphql"

# Map our category buckets -> v2 GraphQL category names (verified against SSE).
DEFAULT_GRAPHQL_CATEGORIES = {
    "weapons": ["Weapons", "Weapons and Armour"],
    "armor": ["Armour", "Weapons and Armour"],
    "new_lands": ["Quests and Adventures", "Dungeons"],
    "graphics": ["Visuals and Graphics", "Models and Textures", "Environmental"],
    "gameplay": ["Gameplay", "Overhauls", "Combat", "Immersion"],
    "followers": ["Followers & Companions"],
    "magic": ["Magic - Spells & Enchantments", "Magic - Gameplay"],
}

_QUERY = """
query Discover($domain: String!, $category: String!, $count: Int!) {
  mods(
    filter: { gameDomainName: {value: $domain, op: EQUALS},
              categoryName: {value: $category, op: EQUALS} }
    sort: [{ endorsements: { direction: DESC } }]
    count: $count
  ) { nodes { modId name summary endorsements downloads version uploader { name }
              pictureUrl adultContent createdAt updatedAt } }
}"""


def _date(v) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def _to_mod(n: dict, domain: str) -> Mod:
    uploader = (n.get("uploader") or {}).get("name", "") or ""
    mid = int(n["modId"])
    return Mod(
        mod_id=mid,
        name=n.get("name", "") or "",
        summary=(n.get("summary") or "").strip(),
        author=uploader,
        uploaded_by=uploader,
        endorsements=int(n.get("endorsements", 0) or 0),
        downloads=int(n.get("downloads", 0) or 0),
        version=str(n.get("version", "") or ""),
        created_at=_date(n.get("createdAt")),
        updated_at=_date(n.get("updatedAt")) or _date(n.get("createdAt")),
        page_url=f"https://www.nexusmods.com/{domain}/mods/{mid}",
        picture_url=n.get("pictureUrl", "") or "",
    )


def discover_mods(domain: str, category_names: list[str], count: int = 60,
                  include_adult: bool = False) -> list[Mod]:
    """Return mods across the given v2 categories, merged + deduped, by endorsements."""
    key = require_env("NEXUS_API_KEY")
    hdr = {"apikey": key, "User-Agent": "skyrim-reviewer/0.1"}
    by_id: dict[int, Mod] = {}
    with httpx.Client(timeout=30.0, headers=hdr) as c:
        for cat in category_names:
            try:
                r = c.post(_V2, json={"query": _QUERY, "variables": {
                    "domain": domain, "category": cat, "count": count}})
                nodes = r.json().get("data", {}).get("mods", {}).get("nodes", []) or []
            except Exception:
                continue
            for n in nodes:
                if n.get("adultContent") and not include_adult:
                    continue
                try:
                    m = _to_mod(n, domain)
                except Exception:
                    continue
                if m.mod_id not in by_id:
                    by_id[m.mod_id] = m
    return sorted(by_id.values(), key=lambda m: m.endorsements, reverse=True)


def graphql_categories_for(category_id: str) -> list[str]:
    """Look up the v2 category names for a bucket (config override, else default)."""
    for c in channel_config().get("categories", []):
        if c.get("id") == category_id and c.get("graphql_categories"):
            return list(c["graphql_categories"])
    return DEFAULT_GRAPHQL_CATEGORIES.get(category_id, [])
