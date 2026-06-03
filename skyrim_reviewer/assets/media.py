"""Asset acquisition stage.

Downloads showable media ONLY for mods the user has recorded as permission-approved
in config/permissions.yaml (see research/nexus.py). For unapproved mods it generates
a neutral placeholder slate so the full pipeline can run end-to-end before you've
secured permissions. Always writes an attribution manifest (CREDITS.md + credits.json).
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import MediaAsset, Mod, Project


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=10))
def _download(url: str, dest: Path) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=30.0) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_bytes():
                fh.write(chunk)


def _placeholder(mod: Mod, dest: Path, size: tuple[int, int]) -> None:
    """Neutral slate for a mod whose media we don't (yet) have permission to show."""
    img = Image.new("RGB", size, (20, 26, 36))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 64)
        small = ImageFont.truetype("DejaVuSans.ttf", 32)
    except Exception:
        font = small = ImageFont.load_default()
    draw.text((size[0] // 2, size[1] // 2 - 40), mod.name, fill=(212, 175, 55),
              anchor="mm", font=font)
    author = mod.uploaded_by or mod.author or "Unknown"
    draw.text((size[0] // 2, size[1] // 2 + 40),
              f"by {author}  —  record gameplay or add permission",
              fill=(160, 160, 160), anchor="mm", font=small)
    img.save(dest)


def acquire_media(project: Project, resolution: tuple[int, int] = (1920, 1080)) -> Project:
    """Populate each mod's media[].local_path; build the attribution manifest."""
    workdir = Path(project.workdir)
    assets_dir = workdir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Optional, OFF by default: pull each approved mod's full image gallery from its
    # Nexus page (the API exposes only one image). This is a ToS-violating scrape —
    # see research/gallery.py and config/permissions.yaml -> allow_gallery_scrape.
    from ..config import channel_config, load_permissions
    perms = load_permissions()
    scrape = bool(perms.get("allow_gallery_scrape", False))
    gallery_max = int(perms.get("gallery_max_images", 6))
    domain = channel_config()["channel"]["game_domain"]

    credits: list[dict] = []
    for mod in project.mods:
        slug = f"mod_{mod.mod_id}"
        used_placeholder = True
        if mod.allow_media_reuse and scrape:
            from ..research.gallery import fetch_gallery
            have = {a.url for a in mod.media}
            if sum(1 for a in mod.media if a.kind == "image") < gallery_max:
                for u in fetch_gallery(mod.mod_id, domain, gallery_max):
                    if u not in have:
                        mod.media.append(MediaAsset(url=u, kind="image"))
                        have.add(u)
            imgs = [a for a in mod.media if a.kind == "image"][:gallery_max]
            mod.media = [a for a in mod.media if a.kind != "image"] + imgs
        if mod.allow_media_reuse and mod.media:
            # Download the approved media.
            for idx, asset in enumerate(mod.media):
                ext = ".jpg" if asset.kind == "image" else ".mp4"
                dest = assets_dir / f"{slug}_{idx}{ext}"
                try:
                    _download(asset.url, dest)
                    asset.local_path = str(dest)
                    used_placeholder = False
                except Exception:
                    asset.local_path = None
        if used_placeholder:
            dest = assets_dir / f"{slug}_placeholder.png"
            _placeholder(mod, dest, resolution)
            mod.media = [MediaAsset(url="", kind="image", local_path=str(dest))]

        credits.append({
            "mod_id": mod.mod_id,
            "name": mod.name,
            "author": mod.uploaded_by or mod.author,
            "page_url": mod.page_url,
            "media_reused": not used_placeholder,
        })

    # Attribution manifest — this is non-negotiable per NexusMods terms.
    (workdir / "credits.json").write_text(json.dumps(credits, indent=2))
    lines = ["# Credits\n",
             "All mods remain the property of their respective authors. "
             "Thank you for your work.\n"]
    for c in credits:
        lines.append(f"- **{c['name']}** by {c['author'] or 'Unknown'} — {c['page_url']}")
    (workdir / "CREDITS.md").write_text("\n".join(lines))
    return project
