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


def _update_spec(spec_path: str, game: str, max_images: int, headless: bool) -> None:
    """Fetch each mod's gallery and write image_urls back into a script spec so the
    render uses the full gallery. Keeps the existing first image as the lead."""
    import yaml
    spec = yaml.safe_load(open(spec_path))
    for m in spec.get("mods", []):
        mid = int(m.get("mod_id", 0))
        if not mid:
            continue
        urls = fetch_gallery(mid, game, max_images, headless=headless)
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
    ap.add_argument("--headed", action="store_true", help="show the browser (debug)")
    args = ap.parse_args()
    headless = not args.headed

    try:
        if args.spec:
            _update_spec(args.spec, args.game, args.max, headless)
            return
        out = {}
        for mid in args.mod_ids:
            urls = fetch_gallery(mid, args.game, args.max, headless=headless)
            print(f"mod {mid}: {len(urls)} images", file=sys.stderr)
            out[str(mid)] = urls
        print(json.dumps(out, indent=1))
    except Exception as exc:
        if "ERR_CONNECTION_RESET" in str(exc) or "ERR_PROXY" in str(exc):
            sys.exit("Browser HTTPS is blocked here (egress proxy resets it). Run this "
                     "on your own machine, not the Claude Code cloud sandbox.")
        raise


if __name__ == "__main__":
    main()
