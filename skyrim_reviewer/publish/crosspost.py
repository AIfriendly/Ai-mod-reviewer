"""Cross-post a Short to TikTok (and optionally more) via upload-post.com.

upload-post.com is a FREE-tier social posting API (10 video uploads/month, one linked
account, no credit card) that posts VIDEO directly to TikTok — no per-platform dev app
or audit on our side, and it accepts the mp4 file directly (no public-URL hosting).

Setup (once, free):
  1. Sign up at https://www.upload-post.com and create a profile ("user"), then connect
     your TikTok account to it in the dashboard.
  2. Copy your API key from the dashboard.
  3. Set these where the pipeline runs (persist them like the Nexus/YouTube vars):
        UPLOAD_POST_API_KEY=...
        UPLOAD_POST_USER=<your profile name from the dashboard>

Then: `skyrim-reviewer crosspost short-adventures-<id>` (or it runs automatically after
a Short is built, when the key is present).

Note: the free tier is one account (TikTok). Add Instagram/YouTube later by connecting
them to the same profile and passing --platforms tiktok,instagram (may need a paid tier).
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx

_UPLOAD_URL = "https://api.upload-post.com/api/upload"


def _creds() -> tuple[str, str]:
    try:
        from ..config import _load_dotenv_once
        _load_dotenv_once()
    except Exception:
        pass
    key = os.environ.get("UPLOAD_POST_API_KEY", "")
    user = os.environ.get("UPLOAD_POST_USER", "")
    if not key or not user:
        missing = [k for k, v in {"UPLOAD_POST_API_KEY": key,
                                  "UPLOAD_POST_USER": user}.items() if not v]
        raise RuntimeError("Missing " + ", ".join(missing) + ". Sign up free at "
                           "upload-post.com, connect TikTok, and set these (see "
                           "publish/crosspost.py).")
    return key, user


def crosspost(video_path: str, caption: str,
              platforms: list[str] | None = None) -> dict:
    """Post a vertical video to `platforms` (default TikTok) via upload-post.com.
    Sends the mp4 file directly. Returns the API response dict."""
    key, user = _creds()
    platforms = platforms or ["tiktok"]
    # form fields; platform[] is repeated once per platform
    data = [("user", user), ("title", caption[:2000])]
    data += [("platform[]", p) for p in platforms]
    with open(video_path, "rb") as fh:
        files = {"video": (Path(video_path).name, fh, "video/mp4")}
        r = httpx.post(_UPLOAD_URL, headers={"Authorization": f"Apikey {key}"},
                       data=data, files=files, timeout=600)
    try:
        body = r.json()
    except Exception:
        body = {"status_code": r.status_code, "text": r.text[:300]}
    if r.status_code >= 400:
        raise RuntimeError(f"upload-post failed ({r.status_code}): {body}")
    return body


def crosspost_slug(slug: str, platforms: list[str] | None = None,
                   out_dir: str = "output") -> dict:
    """Cross-post output/<slug>.mp4 using its title + description as the caption."""
    out = Path(out_dir)
    video = out / f"{slug}.mp4"
    if not video.exists():
        raise FileNotFoundError(f"No video at {video}")
    title_f, desc_f = out / f"{slug}.title.txt", out / f"{slug}.description.txt"
    caption = title_f.read_text(encoding="utf-8").strip() if title_f.exists() else slug
    if desc_f.exists():
        caption += "\n\n" + desc_f.read_text(encoding="utf-8").strip()
    return crosspost(str(video), caption, platforms=platforms)
