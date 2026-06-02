"""Thumbnail generator (1280x720).

Research-backed: big bold 0-3 word text, high contrast, the channel accent, and a
before/after split when two images are available (split-screen converts well for
graphics-mod content). Falls back to a single hero image with a "MODDED" tag.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from ..models import Project

SIZE = (1280, 720)


def _font(size: int, bold: bool = True):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except Exception:
        return ImageFont.load_default()


def _cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    iw, ih = img.size
    scale = max(size[0] / iw, size[1] / ih)
    img = img.resize((int(iw * scale), int(ih * scale)))
    x = (img.size[0] - size[0]) // 2
    y = (img.size[1] - size[1]) // 2
    return img.crop((x, y, x + size[0], y + size[1]))


def _hero_images(project: Project) -> list[str]:
    paths = []
    for mod in project.mods:
        for a in mod.media:
            if a.local_path and Path(a.local_path).suffix.lower() in {
                    ".png", ".jpg", ".jpeg", ".webp"}:
                paths.append(a.local_path)
    return paths


def make_thumbnail(project: Project, text: str | None = None,
                   accent: str = "#d4af37") -> str:
    canvas = Image.new("RGB", SIZE, (12, 18, 26))
    draw = ImageDraw.Draw(canvas)
    heroes = _hero_images(project)
    text = (text or project.script.hook_line if project.script else None) or "TOP MODS"

    if len(heroes) >= 2:
        # Before / after split.
        left = _cover(Image.open(heroes[1]).convert("RGB"), (SIZE[0] // 2, SIZE[1]))
        left = ImageEnhance.Color(left).enhance(0.35)          # desaturate "before"
        right = _cover(Image.open(heroes[0]).convert("RGB"), (SIZE[0] // 2, SIZE[1]))
        canvas.paste(left, (0, 0))
        canvas.paste(right, (SIZE[0] // 2, 0))
        draw.rectangle([SIZE[0] // 2 - 4, 0, SIZE[0] // 2 + 4, SIZE[1]], fill=accent)
        _tag(draw, "VANILLA", (30, 30), (90, 90, 90))
        _tag(draw, "MODDED", (SIZE[0] // 2 + 30, 30), accent)
    elif heroes:
        canvas.paste(_cover(Image.open(heroes[0]).convert("RGB"), SIZE), (0, 0))
        _tag(draw, "MODDED", (SIZE[0] - 250, 30), accent)

    # Darken bottom for text legibility.
    shade = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(shade).rectangle([0, SIZE[1] - 240, SIZE[0], SIZE[1]],
                                    fill=(0, 0, 0, 150))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shade).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # Big bold headline (keep it short).
    words = text.upper().split()
    headline = " ".join(words[:4])
    font = _font(110)
    wrapped = textwrap.fill(headline, width=14)
    draw.multiline_text((50, SIZE[1] - 230), wrapped, font=font, fill="white",
                        stroke_width=6, stroke_fill="black", spacing=4)

    out = Path(project.workdir) / "thumbnail.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    project.thumbnail_path = str(out)
    return str(out)


def _tag(draw, label: str, xy, color) -> None:
    font = _font(40)
    pad = 14
    bbox = draw.textbbox(xy, label, font=font)
    draw.rectangle([bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad],
                   fill=(0, 0, 0))
    draw.text(xy, label, font=font, fill=color)
