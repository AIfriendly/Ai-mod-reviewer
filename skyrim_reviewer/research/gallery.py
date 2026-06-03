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


def fetch_gallery(mod_id: int, domain: str, max_images: int = 6,
                  tries: int = 4, pause: float = 1.0) -> list[str]:
    """Return up to `max_images` full-resolution gallery image URLs for a mod.

    Returns [] on persistent failure (e.g. Cloudflare bot challenge or the website
    being unreachable) — the caller falls back to the single API image.
    """
    url = f"https://www.nexusmods.com/{domain}/mods/{mod_id}?tab=images"
    for attempt in range(tries):
        try:
            r = httpx.get(url, headers={"User-Agent": _UA, "Accept": "text/html",
                                        "Accept-Language": "en-US,en;q=0.9"},
                          timeout=30.0, follow_redirects=True)
            urls = list(dict.fromkeys(_IMG.findall(r.text)))
            if urls:
                time.sleep(pause)          # be polite between mods
                return urls[:max_images]
        except Exception:
            pass
        time.sleep(pause * (attempt + 1))  # backoff through Cloudflare flakiness
    return []
