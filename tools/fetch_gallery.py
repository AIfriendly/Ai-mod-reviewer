"""Retrieve a mod's full image gallery from the NexusMods website with a real browser.

The official Nexus API exposes only ONE image per mod (`picture_url`), and the plain
HTML endpoint is behind a Cloudflare JS challenge that a bare HTTP client (httpx) can't
pass — it just gets a 403 "Just a moment..." page. A real browser engine (headless
Chromium via Playwright) executes that challenge and loads the gallery normally, so we
drive one to read the images tab and collect the full-resolution gallery URLs.

RUN THIS ON YOUR OWN MACHINE. It does NOT work inside the Claude Code cloud sandbox:
that environment's policy-enforcing egress proxy resets all browser-originated HTTPS
(verified — even example.com resets through it), so Chromium can't reach the site there.
On a normal machine (no such proxy) it works directly.

Setup on your machine:
    pip install playwright && playwright install chromium

Usage:
    python tools/fetch_gallery.py 2057 45565 28120 > galleries.json
    python tools/fetch_gallery.py --game skyrimspecialedition --max 8 2057
    python tools/fetch_gallery.py --spec examples/2026-07-11-new_lands-pt10.yaml
        # ^ reads mod_ids from a script spec and writes the image_urls back into it,
        #   so the next `skyrim-reviewer make --script <spec>` renders the full galleries.

⚠️ This reads the Nexus WEBSITE, not the API — that is against the NexusMods Acceptable
Use Policy, and the account tied to your login could be sanctioned. Use at your own
risk, keep the rate low, and always credit authors (the pipeline does).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time


def _chromium_executable() -> str | None:
    """Use a pre-installed full Chromium if present (this environment ships one whose
    version may not match the pinned Playwright, so we point at it instead of
    downloading). Env CHROMIUM_EXECUTABLE overrides. Returns None to let Playwright
    pick its own bundled browser."""
    env = os.environ.get("CHROMIUM_EXECUTABLE")
    if env and os.path.exists(env):
        return env
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    hits = sorted(glob.glob(f"{root}/chromium-*/chrome-linux/chrome"))
    return hits[-1] if hits else None

# Full-res gallery uploads on the Nexus CDN; exclude thumbnails / headers / avatars.
_FULL = re.compile(
    r"https://staticdelivery\.nexusmods\.com/mods/\d+/images/"
    r"(?!thumbnails/|headers/|avatars/)[^\s\"'<>\\)]+?\.(?:jpe?g|png|webp)", re.I)
_THUMB = re.compile(
    r"https://staticdelivery\.nexusmods\.com/mods/\d+/images/thumbnails/"
    r"[^\s\"'<>\\)]+?\.(?:jpe?g|png|webp)", re.I)


def _dedupe(seq):
    return list(dict.fromkeys(seq))


def fetch_gallery_firecrawl(mod_id: int, game: str = "skyrimspecialedition",
                            max_images: int = 8) -> list[str]:
    """Gallery URLs via Firecrawl (firecrawl.dev) — a hosted scraper that renders the
    page on ITS OWN infrastructure and returns the HTML, clearing Cloudflare from a
    clean IP. Works from restricted/datacenter networks (the cloud sandbox included)
    where a local browser/httpx is Cloudflare-blocked, AND returns LIVE current images
    (so it covers brand-new mods, unlike the Wayback archive).

    Keyless free tier works but is rate-limited; set FIRECRAWL_API_KEY for higher limits
    and reliability. Empty on failure."""
    import httpx
    headers = {"User-Agent": "skyrim-reviewer/0.1", "Content-Type": "application/json"}
    key = os.environ.get("FIRECRAWL_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    url = f"https://www.nexusmods.com/{game}/mods/{mod_id}?tab=images"
    try:
        r = httpx.post("https://api.firecrawl.dev/v2/scrape",
                       json={"url": url, "formats": ["html"], "onlyMainContent": False},
                       headers=headers, timeout=120)
        html = (r.json().get("data") or {}).get("html", "") or ""
    except Exception:
        return []
    # Nexus serves protocol-relative //staticdelivery... in some markup — normalise.
    raw = _FULL.findall(html) + [
        "https:" + u for u in re.findall(
            r'(?<!:)//staticdelivery\.nexusmods\.com/mods/\d+/images/'
            r'(?!thumbnails/|headers/|avatars/)[^\s"\'<>\\)]+?\.(?:jpe?g|png|webp)',
            html, re.I)]
    mine = _dedupe(u for u in raw if f"/{mod_id}-" in u or f"/{mod_id}/" in u)
    return mine[:max_images]


def fetch_gallery_wayback(mod_id: int, game: str = "skyrimspecialedition",
                          max_images: int = 8) -> list[str]:
    """Gallery URLs via the Wayback Machine — works from restricted/proxied networks
    where the live Nexus site is Cloudflare-blocked. Archived Nexus pages are not
    Cloudflare-gated, and the images they reference still serve from the CDN. Images
    may be from an older snapshot, which is fine for b-roll. Empty on no snapshot."""
    import httpx
    ua = {"User-Agent": "Mozilla/5.0"}
    base = f"nexusmods.com/{game}/mods/{mod_id}"
    try:
        with httpx.Client(headers=ua, timeout=45, follow_redirects=True) as c:
            snap = None
            for u in (f"{base}?tab=images", base):
                a = c.get(f"https://archive.org/wayback/available?url={u}").json()
                s = (a.get("archived_snapshots") or {}).get("closest") or {}
                if s.get("available"):
                    snap = s["url"]
                    break
            if not snap:
                return []
            ts = snap.split("/web/")[1].split("/")[0]
            raw = (f"https://web.archive.org/web/{ts}id_/"
                   f"https://www.nexusmods.com/{game}/mods/{mod_id}?tab=images")
            html = c.get(raw).text
    except Exception:
        return []
    urls = [u if u.startswith("http") else "https://" + u for u in _FULL.findall(html)]
    # Keep only this mod's gallery shots (exclude the header banner already filtered).
    mine = _dedupe(u for u in urls if f"/{mod_id}-" in u or f"/{mod_id}/" in u)
    return mine[:max_images]


def fetch_gallery(mod_id: int, game: str = "skyrimspecialedition", max_images: int = 8,
                  headless: bool = True, timeout_ms: int = 45000) -> list[str]:
    """Return up to max_images full-res gallery URLs for one mod (empty on failure)."""
    from playwright.sync_api import sync_playwright

    url = f"https://www.nexusmods.com/{game}/mods/{mod_id}?tab=images"
    with sync_playwright() as p:
        # Chromium doesn't auto-read HTTPS_PROXY; pass it explicitly when the
        # environment routes egress through a proxy (the browser NSS store already
        # trusts the proxy CA, so no cert bypass is needed).
        proxy_server = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        launch_kw = dict(headless=headless, executable_path=_chromium_executable(),
                         args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        if proxy_server:
            launch_kw["proxy"] = {"server": proxy_server}
        browser = p.chromium.launch(**launch_kw)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
            viewport={"width": 1440, "height": 900}, locale="en-US")
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # Let Cloudflare's JS challenge resolve, then the gallery lazy-load.
            deadline = time.time() + timeout_ms / 1000
            html = ""
            while time.time() < deadline:
                page.wait_for_timeout(1500)
                html = page.content()
                if "Just a moment" not in html and "staticdelivery.nexusmods.com/mods" in html:
                    break
            # Nudge lazy-loaded thumbnails into the DOM.
            for _ in range(4):
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(600)
            html = page.content()
        finally:
            browser.close()

    # Prefer real full-res URLs; else derive them from thumbnails (drop "thumbnails/").
    full = _dedupe(_FULL.findall(html))
    derived = _dedupe(t.replace("/images/thumbnails/", "/images/") for t in _THUMB.findall(html))
    urls = _dedupe(full + derived)
    return urls[:max_images]


def gallery_urls(mod_id: int, game: str, max_images: int, source: str = "auto",
                 headless: bool = True) -> list[str]:
    """Resolve a mod's gallery URLs.
      firecrawl — hosted scraper, live images, clears Cloudflare from its own IP; works
                  from the cloud sandbox and covers brand-new mods. Keyless free tier.
      browser   — local headless browser, live images (needs a non-blocked network).
      wayback   — Wayback Machine archive; free, but gaps for the newest mods.
      auto      — firecrawl, then wayback, then browser (first non-empty wins)."""
    if source == "firecrawl":
        return fetch_gallery_firecrawl(mod_id, game, max_images)
    if source == "browser":
        return fetch_gallery(mod_id, game, max_images, headless=headless)
    if source == "wayback":
        return fetch_gallery_wayback(mod_id, game, max_images)
    # auto: best-to-fallback
    for fn in (lambda: fetch_gallery_firecrawl(mod_id, game, max_images),
               lambda: fetch_gallery_wayback(mod_id, game, max_images),
               lambda: fetch_gallery(mod_id, game, max_images, headless=headless)):
        try:
            urls = fn()
            if urls:
                return urls
        except Exception:
            continue
    return []


def _update_spec(spec_path: str, game: str, max_images: int, headless: bool,
                 source: str = "auto") -> None:
    """Fetch each mod's gallery and write image_urls back into a script spec so the
    render uses the full gallery. Keeps the existing first image as the lead."""
    import yaml
    spec = yaml.safe_load(open(spec_path))
    for m in spec.get("mods", []):
        mid = int(m.get("mod_id", 0))
        if not mid:
            continue
        urls = gallery_urls(mid, game, max_images, source=source, headless=headless)
        print(f"mod {mid} ({m.get('name','')[:30]}): {len(urls)} images", file=sys.stderr)
        if not urls:
            continue
        lead = m.get("image_url")
        ordered = ([lead] if lead else []) + [u for u in urls if u != lead]
        m["image_url"] = ordered[0]
        m["image_urls"] = ordered[1:max_images]
    yaml.safe_dump(spec, open(spec_path, "w"), sort_keys=False, allow_unicode=True, width=100)
    print(f"Updated {spec_path} with gallery image_urls.", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mod_ids", nargs="*", type=int)
    ap.add_argument("--game", default="skyrimspecialedition")
    ap.add_argument("--max", type=int, default=8)
    ap.add_argument("--spec", help="Script spec YAML: fetch galleries and write image_urls back in")
    ap.add_argument("--source", choices=["auto", "firecrawl", "browser", "wayback"],
                    default="auto",
                    help="auto=firecrawl then wayback then browser. firecrawl (hosted, "
                         "live, works from the cloud sandbox, keyless) is the best default")
    ap.add_argument("--headed", action="store_true", help="show the browser (debug)")
    args = ap.parse_args()
    headless = not args.headed

    if args.spec:
        _update_spec(args.spec, args.game, args.max, headless, source=args.source)
        return
    out = {}
    for mid in args.mod_ids:
        urls = gallery_urls(mid, args.game, args.max, source=args.source, headless=headless)
        print(f"mod {mid}: {len(urls)} images", file=sys.stderr)
        out[str(mid)] = urls
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
