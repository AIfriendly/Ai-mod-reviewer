"""Generate channel brand assets — logo (circular badge), banner, and the thumbnail
brand tag — programmatically with Pillow. Re-run via `skyrim-reviewer brand`.

Brand name + accent come from config/channel.yaml (channel.name, branding.accent_color).
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


def _font(size: int, bold: bool = True):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except Exception:
        return ImageFont.load_default()


def _hex(c: str):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _ctext(draw, cx, y, text, font, fill, stroke=0, stroke_fill=(0, 0, 0)):
    w = draw.textlength(text, font=font)
    draw.text((cx - w / 2, y), text, font=font, fill=fill,
              stroke_width=stroke, stroke_fill=stroke_fill)


def make_logo(name: str, accent: str, out: Path, size: int = 1024) -> str:
    """Circular badge: gold ring, dark centre, brand wordmark + emblem."""
    gold = _hex(accent)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = size / 2
    pad = int(size * 0.04)
    # outer gold ring + dark inner disc
    d.ellipse([pad, pad, size - pad, size - pad], fill=(14, 20, 26, 255),
              outline=gold, width=int(size * 0.045))
    inner = int(size * 0.085)
    d.ellipse([inner, inner, size - inner, size - inner], outline=gold,
              width=int(size * 0.008))

    # Emblem: a stylised "vault keystone" chevron above the wordmark.
    ex, ey, ew = cx, size * 0.26, size * 0.16
    d.polygon([(ex - ew, ey + ew * 0.5), (ex, ey - ew * 0.7), (ex + ew, ey + ew * 0.5),
               (ex + ew * 0.6, ey + ew * 0.5), (ex, ey - ew * 0.15),
               (ex - ew * 0.6, ey + ew * 0.5)], fill=gold)

    # Wordmark — split "Mod" + "Vault" if camelCase, else whole name.
    word = name.replace(" ", "")
    big = _font(int(size * 0.155))
    _ctext(d, cx, size * 0.42, word.upper(), big, (255, 255, 255, 255),
           stroke=int(size * 0.006), stroke_fill=(0, 0, 0, 255))
    # accent underline
    uw = size * 0.30
    d.rectangle([cx - uw / 2, size * 0.605, cx + uw / 2, size * 0.625], fill=gold)
    small = _font(int(size * 0.052))
    _ctext(d, cx, size * 0.645, "GAME MODS · RANKED", small, gold)
    img.save(out)
    return str(out)


def make_banner(name: str, accent: str, out: Path, backdrop: str | None = None,
                tagline: str = "The best game mods, ranked.",
                sub: str = "New videos every week",
                size=(2560, 1440)) -> str:
    """YouTube banner with a darkened backdrop and centred brand block (safe area)."""
    W, H = size
    gold = _hex(accent)
    if backdrop and Path(backdrop).exists():
        bg = Image.open(backdrop).convert("RGB")
        scale = max(W / bg.width, H / bg.height)
        bg = bg.resize((int(bg.width * scale) + 1, int(bg.height * scale) + 1),
                       Image.LANCZOS)
        left, top = (bg.width - W) // 2, (bg.height - H) // 2
        bg = bg.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(14))
        bg = Image.eval(bg, lambda p: int(p * 0.38))
    else:
        bg = Image.new("RGB", size, (12, 16, 22))
    d = ImageDraw.Draw(bg)
    cx, cy = W / 2, H / 2
    word = _font(190)
    _ctext(d, cx, cy - 150, name.upper(), word, (255, 255, 255),
           stroke=8, stroke_fill=(0, 0, 0))
    d.rectangle([cx - 360, cy + 70, cx + 360, cy + 84], fill=gold)
    _ctext(d, cx, cy + 100, tagline, _font(70), gold)
    _ctext(d, cx, cy + 195, sub.upper(), _font(46, bold=False), (220, 220, 220))
    bg.save(out)
    return str(out)
