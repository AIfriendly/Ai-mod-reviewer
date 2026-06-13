"""Render a lower-third credit strip with Pillow (no ImageMagick dependency).

Shows the mod name + author so every featured mod is credited ON SCREEN, as the
NexusMods terms and r/skyrimmods norms require.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def render_lower_third(name: str, author: str, size: tuple[int, int],
                       out_path: Path, accent: str = "#d4af37",
                       rank: int | None = None) -> str:
    W, H = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        big = ImageFont.truetype("DejaVuSans-Bold.ttf", 46)
        small = ImageFont.truetype("DejaVuSans.ttf", 30)
        rankf = ImageFont.truetype("DejaVuSans-Bold.ttf", 78)
    except Exception:
        big = small = rankf = ImageFont.load_default()

    bar_h = 120
    y0 = H - bar_h - 60
    x0 = 60
    accent_rgb = _hex(accent)
    # Big countdown rank badge ("#12") — a clear progression cue that pulls viewers
    # toward the #1 reveal (retention: each entry reads as its own mini-chapter).
    if rank:
        badge = bar_h
        draw.rectangle([x0, y0, x0 + badge, y0 + bar_h], fill=accent_rgb + (235,))
        label = f"#{rank}"
        tb = draw.textbbox((0, 0), label, font=rankf)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        draw.text((x0 + (badge - tw) / 2 - tb[0], y0 + (bar_h - th) / 2 - tb[1]),
                  label, fill=(8, 12, 18, 255), font=rankf)
        x0 += badge + 12

    # translucent backing bar
    draw.rectangle([x0, y0, int(W * 0.66), y0 + bar_h], fill=(10, 16, 24, 200))
    draw.rectangle([x0, y0, x0 + 10, y0 + bar_h], fill=accent_rgb + (255,))
    draw.text((x0 + 30, y0 + 18), name, fill=(255, 255, 255, 255), font=big)
    draw.text((x0 + 30, y0 + 74), f"by {author}", fill=(200, 200, 200, 255), font=small)
    img.save(out_path)
    return str(out_path)


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    except Exception:
        return (212, 175, 55)
