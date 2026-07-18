"""Cross-post a Short to TikTok + Instagram (+ more) via Ayrshare's unified API.

Ayrshare is an audited social-media API: you link your TikTok / Instagram / YouTube
accounts ONCE in its dashboard, and this posts to all of them with a single call — no
per-platform OAuth app or audit on our side (Ayrshare's audit covers direct public
posting).

Setup (once):
  1. Sign up at https://www.ayrshare.com and connect your TikTok + Instagram accounts
     (Instagram must be a Business/Creator account linked to a Facebook Page — that's a
     Meta requirement, not ours).
  2. Copy your API key from the Ayrshare dashboard.
  3. Set it where the pipeline runs (persist it like the Nexus/YouTube vars):
        AYRSHARE_API_KEY=...

Then: `skyrim-reviewer crosspost short-adventures-<id>` (or it runs automatically after
a Short is built, when the key is present).
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx

_BASE = "https://app.ayrshare.com/api"


def _api_key() -> str:
    try:
        from ..config import _load_dotenv_once
        _load_dotenv_once()
    except Exception:
        pass
    key = os.environ.get("AYRSHARE_API_KEY", "")
    if not key:
        raise RuntimeError("AYRSHARE_API_KEY not set. Sign up at ayrshare.com, connect "
                           "TikTok/Instagram, and set the key (see publish/crosspost.py).")
    return key


def _upload_media(path: str, key: str) -> str:
    """Upload the mp4 to Ayrshare's media store and return a public URL to post."""
    fn = Path(path).name
    r = httpx.get(f"{_BASE}/media/uploadUrl",
                  params={"fileName": fn, "contentType": "video/mp4"},
                  headers={"Authorization": f"Bearer {key}"}, timeout=60)
    r.raise_for_status()
    d = r.json()
    upload_url, access_url = d["uploadUrl"], d["accessUrl"]
    with open(path, "rb") as f:
        put = httpx.put(upload_url, content=f.read(),
                        headers={"Content-Type": "video/mp4"}, timeout=None)
    put.raise_for_status()
    return access_url


def crosspost(video_path: str, caption: str,
              platforms: list[str] | None = None,
              media_url: str | None = None) -> dict:
    """Post a vertical video to `platforms` (default TikTok + Instagram Reels). Provide
    a public `media_url` to skip the Ayrshare upload. Returns the API response."""
    key = _api_key()
    platforms = platforms or ["tiktok", "instagram"]
    url = media_url or _upload_media(video_path, key)
    body: dict = {"post": caption[:2200], "platforms": platforms, "mediaUrls": [url]}
    if "instagram" in platforms:
        body["instagramOptions"] = {"reels": True, "shareReelsFeed": True}
    r = httpx.post(f"{_BASE}/post", json=body,
                   headers={"Authorization": f"Bearer {key}",
                            "Content-Type": "application/json"}, timeout=180)
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") \
        else {"status": r.status_code, "text": r.text[:300]}
    if r.status_code >= 400:
        raise RuntimeError(f"Ayrshare post failed ({r.status_code}): {data}")
    return data


def crosspost_slug(slug: str, platforms: list[str] | None = None,
                   out_dir: str = "output") -> dict:
    """Cross-post output/<slug>.mp4 using its generated title + description as caption."""
    out = Path(out_dir)
    video = out / f"{slug}.mp4"
    if not video.exists():
        raise FileNotFoundError(f"No video at {video}")
    title = (out / f"{slug}.title.txt")
    desc = (out / f"{slug}.description.txt")
    caption = (title.read_text(encoding="utf-8").strip() if title.exists() else slug)
    if desc.exists():
        caption += "\n\n" + desc.read_text(encoding="utf-8").strip()
    return crosspost(str(video), caption, platforms=platforms)
