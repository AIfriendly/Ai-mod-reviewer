"""On-screen graphics for the `ranked_tier_list` format: a per-mod scorecard +
"best for" card, and a cumulative S/A/B/C tier board — rendered as static RGBA
PNGs (same technique as lower_third.py / titlecard.py), composited over a short
appended clip after each mod's segment (see ffrender.py's _verdict_clip).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Tier colors, hottest first — matches the visual language of ranking videos
# (S = hot pink/red, cooling down to C). Falls back to grey past D.
TIER_COLORS = {
    "S": (255, 92, 110), "A": (255, 171, 64), "B": (255, 214, 90),
    "C": (255, 240, 150), "D": (200, 200, 205), "F": (150, 150, 155),
}
_DEFAULT_TIER_COLOR = (180, 180, 185)


def _font(size: int, bold: bool = True):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _hex(color: str) -> tuple[int, int, int]:
    c = (color or "").lstrip("#")
    try:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (212, 175, 55)


def _star_row(draw: ImageDraw.ImageDraw, x: int, y: int, score: float, max_score: int,
              size: int, fill, empty, gap: int = 6) -> int:
    """Draw a row of star glyphs for `score` out of `max_score`; returns row width."""
    full = int(score)
    half = (score - full) >= 0.5
    cx = x
    for i in range(max_score):
        filled = i < full or (i == full and half)
        color = fill if (i < full) else (fill if (i == full and half) else empty)
        # Simple 5-point star via polygon.
        pts = _star_points(cx + size / 2, y + size / 2, size / 2)
        draw.polygon(pts, fill=color if filled else None, outline=color)
        cx += size + gap
    return cx - x - gap


def _star_points(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    import math
    pts = []
    for i in range(10):
        ang = math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(ang), cy - rad * math.sin(ang)))
    return pts


def render_scorecard(name: str, scorecard: dict[str, float], size: tuple[int, int],
                      out: Path, accent: str = "#d4af37", max_score: int = 5,
                      title: str = "SCORECARD") -> str:
    """A full-card star-rating breakdown for one mod (RGBA), e.g.:
    IMPACT ***** / UNIQUENESS ****½ / POLISH ***½ / COMPATIBILITY *****
    """
    W, H = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    acc = _hex(accent)
    d.rectangle([0, 0, W, H], fill=(6, 9, 14, 235))

    tf = _font(round(H * 0.075))
    tb = d.textbbox((0, 0), title, font=tf)
    d.text(((W - (tb[2] - tb[0])) // 2, int(H * 0.10)), title, fill=acc, font=tf,
           stroke_width=3, stroke_fill=(0, 0, 0))
    nf = _font(round(H * 0.05), bold=False)
    nb = d.textbbox((0, 0), name, font=nf)
    d.text(((W - (nb[2] - nb[0])) // 2, int(H * 0.20)), name, fill="white", font=nf)

    label_f = _font(round(H * 0.045))
    star_size = round(H * 0.05)
    rows = list(scorecard.items()) or [("Score", 0.0)]
    y = int(H * 0.32)
    row_h = int(H * 0.55 / max(len(rows), 1))
    label_x = int(W * 0.10)
    star_x = int(W * 0.52)
    for label, score in rows:
        d.text((label_x, y), label.upper() + ":", fill="white", font=label_f)
        _star_row(d, star_x, y - round(star_size * 0.12), float(score), max_score,
                  star_size, acc + (255,), (70, 70, 78, 255))
        y += row_h

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return str(out)


def render_best_for(text: str, size: tuple[int, int], out: Path,
                     accent: str = "#d4af37") -> str:
    """A simple "BEST FOR: <who>" card (RGBA), shown alongside/after the scorecard."""
    import textwrap
    W, H = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    acc = _hex(accent)
    kf = _font(round(H * 0.06))
    kb = d.textbbox((0, 0), "BEST FOR", font=kf)
    d.text(((W - (kb[2] - kb[0])) // 2, int(H * 0.40)), "BEST FOR", fill=acc, font=kf)
    bf = _font(round(H * 0.05), bold=False)
    lines = textwrap.fill(text, width=34).split("\n")[:3]
    y = int(H * 0.52)
    for ln in lines:
        lb = d.textbbox((0, 0), ln, font=bf)
        d.text(((W - (lb[2] - lb[0])) // 2, y), ln, fill="white", font=bf,
               stroke_width=2, stroke_fill=(0, 0, 0))
        y += (lb[3] - lb[1]) + 10
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return str(out)


def render_tier_board(placed: list[tuple[str, str]], tiers: list[str],
                       size: tuple[int, int], out: Path,
                       accent: str = "#d4af37", highlight: str | None = None) -> str:
    """The cumulative S/A/B/C board (RGBA) — one row per tier, a small chip per mod
    placed so far (in reveal order). `placed` is [(mod_name, tier), ...]. The most
    recently placed mod (`highlight`, matched by name) gets an accent outline."""
    W, H = size
    board_w = int(W * 0.62)
    row_h = int(H * 0.075)
    board_h = row_h * len(tiers)
    board_x = int(W * 0.03)
    board_y = H - board_h - int(H * 0.05)

    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    label_f = _font(round(row_h * 0.5))
    chip_f = _font(round(row_h * 0.32))

    by_tier: dict[str, list[str]] = {t: [] for t in tiers}
    for name, tier in placed:
        by_tier.setdefault(tier, []).append(name)

    for i, tier in enumerate(tiers):
        y0 = board_y + i * row_h
        color = TIER_COLORS.get(tier, _DEFAULT_TIER_COLOR)
        label_w = row_h
        d.rectangle([board_x, y0, board_x + label_w, y0 + row_h - 3], fill=color + (235,))
        lb = d.textbbox((0, 0), tier, font=label_f)
        d.text((board_x + (label_w - (lb[2] - lb[0])) / 2 - lb[0],
                y0 + (row_h - (lb[3] - lb[1])) / 2 - lb[1]), tier,
               fill=(10, 12, 16, 255), font=label_f)
        d.rectangle([board_x + label_w, y0, board_x + board_w, y0 + row_h - 3],
                    fill=(18, 20, 26, 220))

        cx = board_x + label_w + 12
        for name in by_tier.get(tier, []):
            short = (name[:16] + "…") if len(name) > 17 else name
            cb = d.textbbox((0, 0), short, font=chip_f)
            cw = (cb[2] - cb[0]) + 22
            outline = _hex(accent) + (255,) if name == highlight else (90, 90, 98, 255)
            d.rounded_rectangle([cx, y0 + 8, cx + cw, y0 + row_h - 11], radius=8,
                                fill=(35, 37, 46, 235), outline=outline, width=2)
            d.text((cx + 11 - cb[0], y0 + (row_h - 8 - (cb[3] - cb[1])) / 2 - cb[1]),
                   short, fill="white", font=chip_f)
            cx += cw + 8
            if cx > board_x + board_w - 20:
                break

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return str(out)
