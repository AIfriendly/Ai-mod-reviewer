"""Official game-trailer B-roll from Steam's public store API.

Used for cinematic intro footage. Steam exposes each game's official trailers via
store.steampowered.com/api/appdetails (an HLS/fMP4 stream per trailer). We download
the first N seconds of the GAMEPLAY trailer (not the live-action one, which carries
more third-party Content-ID risk), concatenate the fMP4 segments locally, and remux
to a clean mp4. Cached so it's fetched once.

Footage is the game publisher's IP (here Bethesda). Bethesda permits monetised
Skyrim videos, but trailers can still attract Content-ID claims — keep clips short.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin

import httpx

from ..utils.ffmpeg import configure_moviepy  # noqa: F401

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Steam app ids for the games this channel might cover.
STEAM_APPIDS = {"skyrimspecialedition": 489830, "skyrim": 72850,
                "fallout4": 377160, "starfield": 1716740,
                "oblivionremastered": 2623190}
# Extra app ids to pool for B-roll variety (so the intro montage has different
# source footage to cut between every few seconds).
VARIANT_APPIDS = {"skyrimspecialedition": [489830, 72850],
                  "skyrim": [72850, 489830],
                  "fallout4": [377160]}


def _pick_trailer(movies: list[dict]) -> dict | None:
    """Prefer a gameplay trailer over the live-action one (lower Content-ID risk)."""
    if not movies:
        return None
    gameplay = [m for m in movies if "live action" not in (m.get("name") or "").lower()]
    return (gameplay or movies)[0]


def _variant_720(master_url: str, text: str) -> str:
    """Pick the variant playlist closest to 720p from an HLS master."""
    best, best_diff = None, 1e9
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("#EXT-X-STREAM-INF"):
            m = re.search(r"RESOLUTION=(\d+)x(\d+)", ln)
            height = int(m.group(2)) if m else 0
            uri = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if uri and abs(height - 720) < best_diff:
                best, best_diff = uri, abs(height - 720)
    return urljoin(master_url, best) if best else master_url


def fetch_trailers(domain: str, seconds: float = 40.0,
                   cache_dir: str = "assets_cache") -> list[str]:
    """Return one or more local trailer mp4s to pool as intro B-roll, so the editor
    can cut between different footage. Pulls the gameplay trailer of each related
    Steam app id (e.g. both Skyrim editions). Empty list if nothing fetched."""
    paths = []
    for appid in VARIANT_APPIDS.get(domain, [STEAM_APPIDS.get(domain)]):
        if not appid:
            continue
        p = fetch_trailer(domain, seconds=seconds, cache_dir=cache_dir, appid=appid)
        if p:
            paths.append(p)
    return paths


def fetch_trailer(domain: str, seconds: float = 14.0,
                  cache_dir: str = "assets_cache", appid: int | None = None) -> str | None:
    """Return a local mp4 of the game's official gameplay trailer (~`seconds`),
    or None if it can't be fetched. Result is cached per app id."""
    appid = appid or STEAM_APPIDS.get(domain)
    if not appid:
        return None
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"trailer_{appid}.mp4"
    if out.exists() and out.stat().st_size > 100_000:
        return str(out)

    try:
        with httpx.Client(headers={"User-Agent": _UA}, timeout=30.0,
                          follow_redirects=True) as c:
            data = c.get("https://store.steampowered.com/api/appdetails",
                         params={"appids": appid, "l": "english"}).json()
            movie = _pick_trailer(data[str(appid)]["data"].get("movies", []))
            if not movie or not movie.get("hls_h264"):
                return None
            master_url = movie["hls_h264"]
            variant_url = _variant_720(master_url, c.get(master_url).text)
            playlist = c.get(variant_url).text

            init = re.search(r'#EXT-X-MAP:URI="([^"]+)"', playlist)
            chunks = re.findall(r"^([^#\s].+\.m4s)$", playlist, re.M)
            if not init or not chunks:
                return None
            # ~3s per chunk -> enough chunks to cover `seconds`.
            n = max(1, int(seconds / 3) + 1)
            raw = cache / f"trailer_{appid}_raw.mp4"
            with open(raw, "wb") as f:
                f.write(c.get(urljoin(variant_url, init.group(1))).content)
                for uri in chunks[:n]:
                    f.write(c.get(urljoin(variant_url, uri)).content)
    except Exception:
        return None

    # Remux the LOCAL concatenated fMP4 to a clean mp4 (no network HLS demuxer).
    import subprocess
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        subprocess.run([ff, "-y", "-v", "error", "-i", str(raw), "-t", str(seconds),
                        "-an", "-c:v", "libx264", "-preset", "veryfast",
                        "-pix_fmt", "yuv420p", str(out)],
                       check=True, timeout=180)
    except Exception:
        return None
    finally:
        raw.unlink(missing_ok=True)
    return str(out) if out.exists() else None
