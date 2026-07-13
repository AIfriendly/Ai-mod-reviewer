"""Render a lower-third credit strip with Pillow (no ImageMagick dependency).

Shows the mod name + author (credited ON SCREEN, as NexusMods terms and r/skyrimmods
norms require), plus its endorsement count and a "FREE on Nexus" badge — the kind of
data-credibility on-screen the top mod channels use.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _fmt_endorsements(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return f"{n:,}"


def render_lower_third(name: str, author: str, size: tuple[int, int],
                       out_path: Path, accent: str = "#d4af37",
                       rank: int | None = None, endorsements: int = 0,
                       free_badge: bool = True) -> str:
    W, H = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        big = ImageFont.truetype("DejaVuSans-Bold.ttf", 46)
        small = ImageFont.truetype("DejaVuSans.ttf", 30)
        statf = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
        pillf = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
        rankf = ImageFont.truetype("DejaVuSans-Bold.ttf", 88)
    except Exception:
        big = small = statf = pillf = rankf = ImageFont.load_default()

    bar_h = 138
    y0 = H - bar_h - 56
    x0 = 60
    accent_rgb = _hex(accent)
    # Big countdown rank badge ("#12") — a clear progression cue that pulls viewers
    # toward the #1 reveal (retention: each entry reads as its own mini-chapter).
    if rank:
        badge = bar_h
        draw.rounded_rectangle([x0, y0, x0 + badge, y0 + bar_h], radius=16,
                               fill=accent_rgb + (240,))
        label = f"#{rank}"
        tb = draw.textbbox((0, 0), label, font=rankf)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        draw.text((x0 + (badge - tw) / 2 - tb[0], y0 + (bar_h - th) / 2 - tb[1]),
                  label, fill=(8, 12, 18, 255), font=rankf)
        x0 += badge + 14

    # Translucent info card: name, author, and an endorsement stat line.
    bar_r = int(W * 0.70)
    draw.rounded_rectangle([x0, y0, bar_r, y0 + bar_h], radius=14, fill=(10, 16, 24, 205))
    draw.rectangle([x0, y0 + 14, x0 + 10, y0 + bar_h - 14], fill=accent_rgb + (255,))
    tx = x0 + 30
    draw.text((tx, y0 + 14), name[:38], fill=(255, 255, 255, 255), font=big)
    draw.text((tx, y0 + 72), f"by {author}", fill=(205, 205, 210, 255), font=small)
    if endorsements:
        stat = f"★ {_fmt_endorsements(endorsements)} endorsements"
        aw = draw.textbbox((0, 0), f"by {author}", font=small)[2]
        draw.text((tx + aw + 34, y0 + 76), stat, fill=accent_rgb + (255,), font=statf)

    # "FREE" pill — reinforces the channel's whole promise (every mod is free).
    if free_badge:
        txt = "FREE ON NEXUS"
        pb = draw.textbbox((0, 0), txt, font=pillf)
        pw, ph = pb[2] - pb[0], pb[3] - pb[1]
        px1, py1 = bar_r - pw - 44, y0 - 22
        draw.rounded_rectangle([px1, py1, px1 + pw + 36, py1 + ph + 22], radius=18,
                               fill=accent_rgb + (255,))
        draw.text((px1 + 18, py1 + 9), txt, fill=(10, 14, 20, 255), font=pillf)

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
