"""Auto-upload a finished video to YouTube via the Data API v3 — title, description,
tags, category and a custom thumbnail.

No Google client libraries: it refreshes an OAuth access token and does a resumable
upload directly over HTTPS with httpx (already a dependency). Credentials come from
three environment variables (set them like the Nexus key, so they survive sandbox
recycles) — mint them ONCE with `tools/youtube_auth.py` on a machine with a browser:

    YOUTUBE_CLIENT_ID       OAuth client id  (Google Cloud -> Credentials, Desktop app)
    YOUTUBE_CLIENT_SECRET   OAuth client secret
    YOUTUBE_REFRESH_TOKEN   from the one-time consent helper

⚠️ Un-audited API projects: YouTube LOCKS uploaded videos to `private` until the
project passes Google's API compliance audit. So videos land private by default; make
them public in Studio, or complete the audit for hands-off public publishing. Custom
thumbnails also require the channel to be phone-verified (a one-time YouTube setting).
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
_THUMB_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
_GAMING_CATEGORY = "20"          # YouTube's "Gaming" category id


def _creds() -> tuple[str, str, str]:
    cid = os.environ.get("YOUTUBE_CLIENT_ID", "")
    secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    refresh = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    missing = [k for k, v in {"YOUTUBE_CLIENT_ID": cid, "YOUTUBE_CLIENT_SECRET": secret,
                              "YOUTUBE_REFRESH_TOKEN": refresh}.items() if not v]
    if missing:
        raise RuntimeError(
            "Missing YouTube OAuth env vars: " + ", ".join(missing) +
            ". Run tools/youtube_auth.py once to mint them.")
    return cid, secret, refresh


def _access_token() -> str:
    cid, secret, refresh = _creds()
    r = httpx.post(_TOKEN_URL, data={
        "client_id": cid, "client_secret": secret,
        "refresh_token": refresh, "grant_type": "refresh_token"}, timeout=60)
    r.raise_for_status()
    return r.json()["access_token"]


def _file_chunks(path: str, size: int = 1024 * 1024):
    with open(path, "rb") as f:
        while True:
            b = f.read(size)
            if not b:
                break
            yield b


def set_thumbnail(video_id: str, thumb_path: str, token: str | None = None) -> None:
    token = token or _access_token()
    ct = "image/png" if thumb_path.lower().endswith(".png") else "image/jpeg"
    data = Path(thumb_path).read_bytes()
    r = httpx.post(_THUMB_URL, params={"videoId": video_id},
                   headers={"Authorization": f"Bearer {token}", "Content-Type": ct},
                   content=data, timeout=120)
    r.raise_for_status()


def upload_video(video_path: str, title: str, description: str,
                 tags: list[str] | None = None, category_id: str = _GAMING_CATEGORY,
                 privacy: str = "private", thumbnail_path: str | None = None,
                 publish_at: str | None = None) -> dict:
    """Resumable-upload a video and (optionally) set its thumbnail. Returns
    {video_id, url, privacy}. `publish_at` (RFC3339, e.g. 2026-07-20T15:00:00Z)
    schedules a public go-live — only honoured once the project is audited."""
    token = _access_token()
    size = os.path.getsize(video_path)
    status: dict = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
    if publish_at:
        status["privacyStatus"] = "private"      # required alongside publishAt
        status["publishAt"] = publish_at
    meta = {"snippet": {"title": title[:100], "description": description[:5000],
                        "tags": tags or [], "categoryId": category_id},
            "status": status}
    # 1) init resumable session
    init = httpx.post(_UPLOAD_URL,
                      params={"uploadType": "resumable", "part": "snippet,status"},
                      headers={"Authorization": f"Bearer {token}",
                               "X-Upload-Content-Type": "video/*",
                               "X-Upload-Content-Length": str(size)},
                      json=meta, timeout=60)
    init.raise_for_status()
    session_url = init.headers.get("Location")
    if not session_url:
        raise RuntimeError("YouTube did not return a resumable upload URL")
    # 2) stream the bytes
    put = httpx.put(session_url, content=_file_chunks(video_path),
                    headers={"Content-Type": "video/*", "Content-Length": str(size)},
                    timeout=None)
    put.raise_for_status()
    vid = put.json()["id"]
    if thumbnail_path and Path(thumbnail_path).exists():
        try:
            set_thumbnail(vid, thumbnail_path, token)
        except Exception as e:                    # thumbnail needs a verified channel
            print(f"  [youtube] video uploaded but thumbnail failed: {e}")
    return {"video_id": vid, "url": f"https://youtu.be/{vid}",
            "privacy": status["privacyStatus"]}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def publish_slug_youtube(slug: str, privacy: str = "private",
                         publish_at: str | None = None, out_dir: str = "output") -> dict:
    """Upload output/<slug>.mp4 using its generated title/description/tags + thumbnail."""
    out = Path(out_dir)
    video = out / f"{slug}.mp4"
    if not video.exists():
        raise FileNotFoundError(f"No rendered video at {video}")
    title = _read(out / f"{slug}.title.txt") or slug
    description = _read(out / f"{slug}.description.txt")
    tags_raw = _read(out / f"{slug}.tags.txt")
    tags = [t.strip() for t in tags_raw.replace("\n", ",").split(",") if t.strip()]
    # thumbnail: prefer the first A/B variant, else the single thumbnail.png
    thumb = next(iter(sorted(Path(f"work/{slug}/thumbs").glob("thumb_v*.png"))), None) \
        or (Path(f"work/{slug}/thumbnail.png") if Path(f"work/{slug}/thumbnail.png").exists()
            else None)
    res = upload_video(str(video), title, description, tags, privacy=privacy,
                       thumbnail_path=str(thumb) if thumb else None,
                       publish_at=publish_at)
    res["title"] = title
    return res
