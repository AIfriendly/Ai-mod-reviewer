"""Live reference-channel research via Firecrawl.

`config/reference_channels.yaml` is a static, hand-curated list of formats
these channels are known for. This module optionally freshens `ideas --live`
with what a reference channel is *currently* publishing, via Firecrawl's web
search (no scraping/HTML parsing of our own — Firecrawl returns titles
directly). Best-effort only: `ideas` must keep working with no key set or on
any Firecrawl failure.
"""
from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import get_env

API_URL = "https://api.firecrawl.dev/v1/search"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _search(query: str, limit: int) -> list[dict]:
    api_key = get_env("FIRECRAWL_API_KEY")
    if not api_key:
        return []
    resp = httpx.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": query, "limit": limit},
        timeout=20.0,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def live_channel_titles(channel_name: str, limit: int = 5) -> list[str]:
    """Current video titles for a reference channel's YouTube uploads.

    Returns [] if `FIRECRAWL_API_KEY` isn't set or the call fails for any
    reason — this is an optional freshness layer, never a hard dependency.
    """
    try:
        results = _search(f'site:youtube.com "{channel_name}" skyrim mods', limit)
    except Exception:
        return []
    return [r["title"] for r in results if r.get("title")]
