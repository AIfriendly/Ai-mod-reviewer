"""PIL-rendered title / intro / outro cards — no Node/Remotion needed.

Hook, intro and outro segments have no mod image, so without this they render as a
blank dark frame. This draws the video title (and a subtitle/CTA) over a softly
blurred backdrop of a mod screenshot, with an accent underline.
"""
from __future__ import annotations

import textwrap

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


def _font(size: int, bold: bool = False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except Exception:
        return ImageFont.load_default()


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _backdrop(size: tuple[int, int], bg_image: str | None) -> Image.Image:
    W, H = size
    if bg_image:
        try:
            im = Image.open(bg_image).convert("RGB")
            scale = max(W / im.width, H / im.height)
            im = im.resize((int(im.width * scale) + 1, int(im.height * scale) + 1),
                           Image.LANCZOS)
            left, top = (im.width - W) // 2, (im.height - H) // 2
            im = im.crop((left, top, left + W, top + H))
            im = im.filter(ImageFilter.GaussianBlur(28))
            return Image.eval(im, lambda p: int(p * 0.40))
        except Exception:
            pass
    # Fallback: dark vertical gradient.
    base = Image.new("RGB", size, (12, 16, 24))
    top = np.linspace(28, 10, H).astype("uint8")
    arr = np.zeros((H, W, 3), "uint8")
    for i, v in enumerate(top):
        arr[i, :] = (v, int(v * 1.1), int(v * 1.4))
    return Image.fromarray(arr)


def title_card_array(title: str, subtitle: str, size: tuple[int, int],
                     accent: str = "#d4af37", bg_image: str | None = None) -> np.ndarray:
    W, H = size
    img = _backdrop(size, bg_image).convert("RGB")
    draw = ImageDraw.Draw(img)

    title_f = _font(max(40, W // 18), bold=True)
    sub_f = _font(max(22, W // 48))

    lines = textwrap.wrap(title.upper(), width=22) or [""]
    line_h = title_f.size + 14
    block_h = len(lines) * line_h
    y = (H - block_h) // 2 - 20

    for ln in lines:
        w = draw.textlength(ln, font=title_f)
        x = (W - w) // 2
        draw.text((x + 3, y + 3), ln, font=title_f, fill=(0, 0, 0))   # shadow
        draw.text((x, y), ln, font=title_f, fill=(255, 255, 255))
        y += line_h

    # accent underline
    bar_w = int(W * 0.18)
    draw.rectangle([(W - bar_w) // 2, y + 6, (W + bar_w) // 2, y + 14], fill=_hex(accent))

    if subtitle:
        w = draw.textlength(subtitle, font=sub_f)
        draw.text(((W - w) // 2, y + 34), subtitle, font=sub_f, fill=(220, 220, 220))

    return np.asarray(img)


def title_overlay_rgba(title: str, subtitle: str, size: tuple[int, int],
                       accent: str = "#d4af37") -> np.ndarray:
    """Transparent overlay (RGBA) for laying a title over live footage: a bottom-up
    dark scrim for legibility + centered title + accent underline."""
    W, H = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    # Bottom-weighted gradient scrim so text stays readable over any footage.
    scrim = np.zeros((H, W, 4), "uint8")
    col = np.linspace(0, 200, H).astype("uint8")          # transparent top -> dark base
    scrim[..., 3] = col[:, None]
    img = Image.alpha_composite(img, Image.fromarray(scrim))
    draw = ImageDraw.Draw(img)

    title_f = _font(max(40, W // 18), bold=True)
    sub_f = _font(max(22, W // 48))
    lines = textwrap.wrap(title.upper(), width=22) or [""]
    line_h = title_f.size + 14
    y = int(H * 0.60)
    for ln in lines:
        w = draw.textlength(ln, font=title_f)
        x = (W - w) // 2
        draw.text((x + 3, y + 3), ln, font=title_f, fill=(0, 0, 0, 255))
        draw.text((x, y), ln, font=title_f, fill=(255, 255, 255, 255))
        y += line_h
    bar_w = int(W * 0.18)
    draw.rectangle([(W - bar_w) // 2, y + 6, (W + bar_w) // 2, y + 14], fill=_hex(accent))
    if subtitle:
        w = draw.textlength(subtitle, font=sub_f)
        draw.text(((W - w) // 2, y + 34), subtitle, font=sub_f, fill=(220, 220, 220, 255))
    return np.asarray(img)
