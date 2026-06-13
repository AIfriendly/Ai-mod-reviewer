"""Mod-page image gallery fetcher.

⚠️ TERMS-OF-SERVICE WARNING. Unlike the rest of this project, this module reads the
NexusMods *website* (not the official API) to collect a mod's full image gallery,
which the API does not expose (it returns only one `picture_url` per mod). Reading
the website this way is against the NexusMods API Acceptable Use Policy / ToS, and
the personal API key in use is tied to a Nexus account that could be banned. It is
therefore OFF by default and gated behind `allow_gallery_scrape` in
config/permissions.yaml. It only ever runs for mods whose author you've approved,
and authors are still credited on screen and in the description.

It is also polite: a browser User-Agent, retries with backoff, and only the gallery
upload URLs (no thumbnails/banners).
"""
from __future__ import annotations

import re
import time

import httpx

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Full-resolution gallery uploads on the Nexus CDN, excluding thumbnails, page
# banners (/headers/) and user avatars (/avatars/).
_IMG = re.compile(
    r"https://staticdelivery\.nexusmods\.com/mods/\d+/images/"
    r"(?!thumbnails/|headers/|avatars/)[^\s\"<>\\]+?\.(?:jpe?g|png|webp)", re.I)

# Author-uploaded gallery videos on the Nexus CDN (mp4/webm). Many mods have none
# (they embed YouTube instead); we only ever use these self-hosted files.
_VID = re.compile(
    r"https://staticdelivery\.nexusmods\.com/mods/\d+/(?:videos|images)/"
    r"[^\s\"<>\\]+?\.(?:mp4|webm)", re.I)


def _fetch_html(mod_id: int, domain: str, tries: int, pause: float) -> str:
    url = f"https://www.nexusmods.com/{domain}/mods/{mod_id}?tab=images"
    for attempt in range(tries):
        try:
            r = httpx.get(url, headers={"User-Agent": _UA, "Accept": "text/html",
                                        "Accept-Language": "en-US,en;q=0.9"},
                          timeout=30.0, follow_redirects=True)
            if r.text:
                return r.text
        except Exception:
            pass
        time.sleep(pause * (attempt + 1))  # backoff through Cloudflare flakiness
    return ""


def fetch_gallery(mod_id: int, domain: str, max_images: int = 6,
                  tries: int = 4, pause: float = 1.0) -> list[str]:
    """Return up to `max_images` full-resolution gallery image URLs for a mod.

    Returns [] on persistent failure (e.g. Cloudflare bot challenge or the website
    being unreachable) — the caller falls back to the single API image.
    """
    html = _fetch_html(mod_id, domain, tries, pause)
    urls = list(dict.fromkeys(_IMG.findall(html)))
    if urls:
        time.sleep(pause)                  # be polite between mods
    return urls[:max_images]


def fetch_gallery_media(mod_id: int, domain: str, max_images: int = 6,
                        max_videos: int = 1, tries: int = 4,
                        pause: float = 1.0) -> dict:
    """Return {'images': [...], 'videos': [...]} from a SINGLE page fetch.

    Videos are author-uploaded files hosted on the Nexus CDN only — usually absent,
    in which case 'videos' is empty and the renderer falls back to the still gallery.
    """
    html = _fetch_html(mod_id, domain, tries, pause)
    if not html:
        return {"images": [], "videos": []}
    images = list(dict.fromkeys(_IMG.findall(html)))[:max_images]
    videos = list(dict.fromkeys(_VID.findall(html)))[:max_videos]
    if images or videos:
        time.sleep(pause)                  # be polite between mods
    return {"images": images, "videos": videos}
