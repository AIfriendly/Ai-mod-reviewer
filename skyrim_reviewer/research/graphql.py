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
    # "Locations -  New" (sic, double space — official Nexus category name) is where
    # dedicated new-worldspace mods actually live (Falskaar, Wyrmstooth, etc.) — the
    # single biggest source of real new-lands content. Missing it silently starved
    # this bucket to a handful of leftovers found only via Quests and Adventures.
    "new_lands": ["Locations -  New", "Quests and Adventures"],
    # filtered to true new lands / pure quests respectively in autospec.py
    "quests": ["Quests and Adventures"],       # filtered to pure quest mods in autospec
    "graphics": ["Visuals and Graphics", "Models and Textures", "Environmental"],
    "gameplay": ["Gameplay", "Overhauls", "Combat", "Immersion"],
    "followers": ["Followers & Companions"],
    "magic": ["Magic - Spells & Enchantments", "Magic - Gameplay"],
}

_QUERY = """
query Discover($domain: String!, $category: String!, $count: Int!, $offset: Int!) {
  mods(
    filter: { gameDomainName: {value: $domain, op: EQUALS},
              categoryName: {value: $category, op: EQUALS} }
    sort: [{ endorsements: { direction: DESC } }]
    count: $count
    offset: $offset
  ) { nodes { modId name summary description endorsements downloads version
              uploader { name }
              pictureUrl adultContent createdAt updatedAt } }
}"""

_PAGE = 80   # the v2 API caps a single page at ~80 nodes


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
        description=(n.get("description") or "").strip(),
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
                  include_adult: bool = False, pages: int = 1) -> list[Mod]:
    """Return mods across the given v2 categories, merged + deduped, by endorsements.

    `pages` walks the catalogue deeper (each page ≈80 mods by descending endorsements).
    pages=1 keeps the top slice; a long numbered series uses many pages to reach the
    thousands of quest/dungeon mods past the popular front page.
    """
    key = require_env("NEXUS_API_KEY")
    hdr = {"apikey": key, "User-Agent": "skyrim-reviewer/0.1"}
    page_size = _PAGE if pages > 1 else min(count, _PAGE)
    by_id: dict[int, Mod] = {}
    with httpx.Client(timeout=30.0, headers=hdr) as c:
        for cat in category_names:
            for p in range(max(1, pages)):
                try:
                    r = c.post(_V2, json={"query": _QUERY, "variables": {
                        "domain": domain, "category": cat, "count": page_size,
                        "offset": p * page_size}})
                    nodes = r.json().get("data", {}).get("mods", {}).get("nodes", []) or []
                except Exception:
                    break
                if not nodes:
                    break                       # past the end of this category
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
