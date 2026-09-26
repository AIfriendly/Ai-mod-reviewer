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
    # Stop at 0.72: render_best_for owns the band below, and the two cards are
    # composited over each other, so overrunning here collides with its text.
    row_h = int(H * 0.40 / max(len(rows), 1))
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
    d.text(((W - (kb[2] - kb[0])) // 2, int(H * 0.755)), "BEST FOR", fill=acc, font=kf)
    bf = _font(round(H * 0.05), bold=False)
    lines = textwrap.fill(text, width=34).split("\n")[:3]
    y = int(H * 0.835)
    for ln in lines:
        lb = d.textbbox((0, 0), ln, font=bf)
        d.text(((W - (lb[2] - lb[0])) // 2, y), ln, fill="white", font=bf,
               stroke_width=2, stroke_fill=(0, 0, 0))
        y += (lb[3] - lb[1]) + 10
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return str(out)


def _thumb(path: str | None, s: int) -> Image.Image:
    """A square cover-cropped thumbnail, or a neutral plate when the image is missing."""
    if path and Path(path).exists():
        try:
            im = Image.open(path).convert("RGB")
            w, h = im.size
            side = min(w, h)
            im = im.crop(((w - side) // 2, (h - side) // 2,
                          (w + side) // 2, (h + side) // 2))
            return im.resize((s, s), Image.LANCZOS)
        except Exception:
            pass
    return Image.new("RGB", (s, s), (38, 41, 50))


def _fit_thumb_size(counts: list[int], avail_w: int, avail_h: int,
                    label_w: int, gap: int, n_tiers: int) -> tuple[int, int]:
    """Largest square thumb size that lets EVERY placed mod fit on one screen, with
    the number of columns it implies. Tiers wrap onto extra lines as they fill, and
    each line costs height, so this walks sizes down until the whole board fits."""
    for s in range(min(avail_h // max(n_tiers, 1), 260), 15, -2):
        cols = max(1, (avail_w - label_w - gap) // (s + gap))
        total = 0
        for n in counts:
            lines = max(1, -(-n // cols))          # ceil
            total += lines * (s + gap) + gap
        if total <= avail_h:
            return s, cols
    s = 16
    return s, max(1, (avail_w - label_w - gap) // (s + gap))


def render_tier_board(placed: list[tuple[str, str, str | None]], tiers: list[str],
                       size: tuple[int, int], out: Path,
                       accent: str = "#d4af37", highlight: str | None = None) -> str:
    """The cumulative S..F board (RGBA), drawn FULL SCREEN with a thumbnail per mod.

    `placed` is [(mod_name, tier, image_path), ...] in reveal order; the most recent
    entry (`highlight`, matched by name) gets an accent outline. Thumbnails are sized
    to fit every placed mod on screen at once — a hundred-mod board just packs smaller
    rather than dropping the overflow, which is what the old text-chip strip did.
    """
    W, H = size
    img = Image.new("RGBA", size, (8, 10, 15, 244))
    d = ImageDraw.Draw(img)

    pad = int(H * 0.035)
    title_f = _font(round(H * 0.055))
    title = "THE TIER LIST"
    tb = d.textbbox((0, 0), title, font=title_f)
    d.text(((W - (tb[2] - tb[0])) // 2 - tb[0], pad - tb[1]), title,
           fill=_hex(accent), font=title_f, stroke_width=3, stroke_fill=(0, 0, 0))

    top = pad + (tb[3] - tb[1]) + int(H * 0.025)
    avail_w, avail_h = W - pad * 2, H - top - pad
    gap = max(3, int(H * 0.006))
    label_w = int(W * 0.055)

    by_tier: dict[str, list[tuple[str, str | None]]] = {t: [] for t in tiers}
    for name, tier, image in placed:
        by_tier.setdefault(tier, []).append((name, image))

    counts = [len(by_tier.get(t, [])) for t in tiers]
    s, cols = _fit_thumb_size(counts, avail_w, avail_h, label_w, gap, len(tiers))
    label_f = _font(max(14, round(s * 0.62)))

    # Rows are usually width-bound (a full tier fits on one line long before it fills
    # the height), so centre the block instead of letting it hang from the title.
    row_heights = [max(1, -(-len(by_tier.get(t, [])) // cols)) * (s + gap) + gap
                   for t in tiers]
    y = top + max(0, (avail_h - sum(row_heights)) // 2)
    for tier, row_h in zip(tiers, row_heights):
        items = by_tier.get(tier, [])
        color = TIER_COLORS.get(tier, _DEFAULT_TIER_COLOR)
        d.rectangle([pad, y, pad + label_w, y + row_h - gap], fill=color + (240,))
        lb = d.textbbox((0, 0), tier, font=label_f)
        d.text((pad + (label_w - (lb[2] - lb[0])) / 2 - lb[0],
                y + (row_h - gap - (lb[3] - lb[1])) / 2 - lb[1]), tier,
               fill=(10, 12, 16, 255), font=label_f)
        d.rectangle([pad + label_w + gap, y, W - pad, y + row_h - gap],
                    fill=(18, 20, 26, 230))

        for k, (name, image) in enumerate(items):
            cx = pad + label_w + gap * 2 + (k % cols) * (s + gap)
            cy = y + gap + (k // cols) * (s + gap)
            img.paste(_thumb(image, s), (cx, cy))
            if name == highlight:
                d.rectangle([cx - 2, cy - 2, cx + s + 1, cy + s + 1],
                            outline=_hex(accent) + (255,), width=max(2, s // 22))
        y += row_h

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return str(out)
