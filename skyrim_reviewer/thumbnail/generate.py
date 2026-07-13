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


def _mod_main_image(mod) -> str | None:
    """The author-curated main/splash image (media[0]) — the most striking shot, and
    far less likely to be a stats table or UI screenshot than a random gallery pic."""
    for a in mod.media:
        if a.local_path and Path(a.local_path).suffix.lower() in {
                ".png", ".jpg", ".jpeg", ".webp"}:
            return a.local_path
    return None


def _brightness(path: str) -> float:
    """Mean luminance (0-255) of an image, sampled small for speed. -1 on error."""
    try:
        im = Image.open(path).convert("L")
        im.thumbnail((64, 64))
        px = list(im.getdata())
        return sum(px) / len(px) if px else -1
    except Exception:
        return -1


def _contrast(path: str) -> float:
    """Std-dev of luminance — low values mean a flat/hazy shot that reads as muddy."""
    try:
        im = Image.open(path).convert("L")
        im.thumbnail((96, 96))
        px = list(im.getdata())
        n = len(px) or 1
        mean = sum(px) / n
        return (sum((p - mean) ** 2 for p in px) / n) ** 0.5
    except Exception:
        return -1


def _subject_score(path: str) -> float:
    """How strongly an image features a character/face subject (0 = none).

    Uses OpenCV Haar cascades when available — character close-ups make far stronger
    thumbnails (faces lift CTR ~20-30%). Degrades to 0.0 if OpenCV isn't installed,
    so selection simply falls back to the editorial/well-lit logic."""
    try:
        import os
        import cv2
        import numpy as np
        im = Image.open(path).convert("L")
        im.thumbnail((480, 480))
        arr = np.asarray(im)
        data = os.path.join(os.path.dirname(cv2.__file__), "data")
        best = 0.0
        for name in ("haarcascade_frontalface_alt2.xml",
                     "haarcascade_profileface.xml"):
            c = cv2.CascadeClassifier(os.path.join(data, name))
            if c.empty():
                continue
            faces = c.detectMultiScale(arr, scaleFactor=1.1, minNeighbors=5,
                                       minSize=(40, 40))
            for (x, y, w, h) in faces:
                # Bigger faces (close-ups) score higher; relative to frame area.
                best = max(best, (w * h) / float(arr.shape[0] * arr.shape[1]))
        return best
    except Exception:
        return 0.0


def _text_coverage(path: str) -> float:
    """Fraction of the frame occupied by baked-in TEXT (0-1). Mod splash/primary images
    are frequently 'title cards' with the mod name written across them (and sometimes a
    2- or 3-panel collage) — layering our own thumbnail text on top of those makes a
    cluttered mess. This detects those so we can reject them as the hero. Uses a
    morphological-gradient text-region heuristic via OpenCV; returns 0.0 if unavailable
    (selection then just falls back to the brightness/subject logic).

    Calibrated: title cards score ~0.08-0.15, clean gameplay screenshots ~0.00-0.03."""
    try:
        import cv2
        import numpy as np
        im = Image.open(path).convert("L")
        im.thumbnail((640, 360))
        arr = np.asarray(im)
        h, w = arr.shape
        grad = cv2.morphologyEx(arr, cv2.MORPH_GRADIENT,
                                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        connected = cv2.morphologyEx(bw, cv2.MORPH_CLOSE,
                                     cv2.getStructuringElement(cv2.MORPH_RECT, (11, 1)))
        cnts, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
        area = 0
        for c in cnts:
            x, y, cw, ch = cv2.boundingRect(c)
            ar = cw / float(ch) if ch else 0
            # text lines read as wide, short, stroke-dense boxes (not full-frame edges)
            if 1.8 < ar < 30 and 0.03 * h < ch < 0.22 * h and cw > 0.08 * w:
                if bw[y:y + ch, x:x + cw].mean() > 45:
                    area += cw * ch
        return min(1.0, area / float(w * h))
    except Exception:
        return 0.0


_TEXT_MAX = 0.045   # reject a hero whose text coverage exceeds this (title cards)


def _hero_quality(path: str) -> float:
    """Higher = a better thumbnail hero. Rewards a well-exposed, punchy image and
    penalises dark/underexposed or flat/hazy shots (which read as muddy at small size).
    Keeps selection away from gloomy interior/HUD screenshots."""
    b = _brightness(path)
    if b < 0:
        return -1.0
    # brightness sweet-spot ~130; falls off toward black/blown-out
    bright = 1.0 - abs(b - 130) / 130.0
    contrast = min(_contrast(path) / 70.0, 1.0)     # 70+ std-dev = plenty of punch
    return 0.55 * bright + 0.45 * contrast


def _clean_heroes(mod) -> list[str]:
    """A mod's screenshots that are NOT title-card/text-heavy, ranked best-hero first
    by exposure/contrast quality (so dark HUD screenshots lose to bright promo shots).
    Primaries are eligible but only if clean."""
    imgs = [a.local_path for a in mod.media
            if a.local_path and Path(a.local_path).suffix.lower() in {
                ".png", ".jpg", ".jpeg", ".webp"} and Path(a.local_path).exists()]
    if not imgs:
        return []
    gallery, primary = imgs[1:], imgs[:1]
    ordered = gallery + primary                    # prefer gallery over the splash
    clean = [p for p in ordered if _text_coverage(p) <= _TEXT_MAX] or ordered
    return sorted(clean, key=_hero_quality, reverse=True)


def _mod_gallery_hero(mod) -> str | None:
    """The best clean, well-exposed GALLERY screenshot for the hero."""
    clean = _clean_heroes(mod)
    return clean[0] if clean else None


def _best_hero(project: Project) -> str | None:
    """Pick the thumbnail hero: a clean (text-free), well-lit, high-contrast GALLERY
    screenshot from the top-endorsed mods, preferring a clear character/face subject
    (close-ups convert best). Never a title-card splash image."""
    ranked = sorted(project.mods, key=lambda m: getattr(m, "endorsements", 0),
                    reverse=True)
    candidates = [img for mod in ranked[:10] for img in _clean_heroes(mod)[:2]]
    if not candidates:
        candidates = _hero_images(project)
    if not candidates:
        return None
    well_lit = [img for img in candidates if 55 <= _brightness(img) <= 215] or candidates
    # Prefer a prominent subject/face if one is clearly present (>~4% of the frame).
    subjects = [(img, _subject_score(img)) for img in well_lit]
    strong = [(img, s) for img, s in subjects if s >= 0.04]
    if strong:
        return max(strong, key=lambda x: x[1])[0]
    # else the punchiest (highest-contrast) well-lit shot — reads best at small size.
    return max(well_lit, key=_contrast)


def make_thumbnail(project: Project, text: str | None = None,
                   accent: str = "#d4af37", category_title: str = "") -> str:
    """Channel-style thumbnail. Renders via Remotion when available (split panels,
    accent keyword, banner, ESRB badge, border); falls back to the PIL design."""
    out = Path(project.workdir) / "thumbnail.png"
    heroes = _hero_images(project)
    if heroes:
        from ..branding import thumbnail_text
        from ..edit.remotion_render import render_thumbnail
        title = (project.script.title if project.script else "") or "Best Skyrim Mods"
        cid = getattr(project, "category_id", "") or ""
        headline, keyword, banner = thumbnail_text(title, category_title or title, cid)
        # Single epic hero: the MAIN (author-curated) image of the most-endorsed mod —
        # the most striking shot, and never a stats table / UI screenshot.
        hero = _best_hero(project)
        from ..config import channel_config as _cc
        brand = _cc().get('channel', {}).get('name', '')
        if render_thumbnail(headline, keyword, banner, [hero] if hero else heroes,
                            accent, out, brand=brand, count=len(project.mods)):
            project.thumbnail_path = str(out)
            return str(out)

    # PIL fallback (used when Remotion isn't available — e.g. the cloud sandbox).
    cid = getattr(project, "category_id", "") or ""
    kw = _keyword_for(cid, project)
    out.parent.mkdir(parents=True, exist_ok=True)
    _pil_thumbnail([_best_hero(project)] + heroes, kw, accent, len(project.mods), cid, out)
    project.thumbnail_path = str(out)
    return str(out)


def _keyword_for(category_id: str, project) -> str:
    """Short, punchy 1-2 word thumbnail keyword by category."""
    return {"new_lands": "NEW LANDS", "quests": "NEW QUESTS", "graphics": "NEXT-GEN",
            "weapons": "WEAPONS", "armor": "ARMOR", "magic": "MAGIC",
            "gameplay": "OVERHAUL", "followers": "FOLLOWERS"}.get(
        category_id, "MODS")


def _tag(draw, label: str, xy, color, font_size: int = 40) -> None:
    font = _font(font_size)
    pad = 14
    bbox = draw.textbbox(xy, label, font=font)
    draw.rectangle([bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad],
                   fill=(0, 0, 0))
    draw.text(xy, label, font=font, fill=color)


def _punch(img: Image.Image) -> Image.Image:
    """Boost contrast + saturation so the hero pops at thumbnail size."""
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Color(img).enhance(1.25)
    img = ImageEnhance.Brightness(img).enhance(1.03)
    return img


def _vignette(canvas: Image.Image, strength: int = 150) -> Image.Image:
    """Darken the edges/corners so the centre subject pops (cinematic focus)."""
    W, H = canvas.size
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    # radial-ish falloff via nested ellipses
    steps = 40
    for i in range(steps):
        a = int(strength * (i / steps) ** 2)
        pad = int((i / steps) * min(W, H) * 0.75)
        md.ellipse([-pad, -pad, W + pad, H + pad], outline=a)
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dark.putalpha(mask)
    return Image.alpha_composite(canvas.convert("RGBA"), dark).convert("RGB")


def _pil_thumbnail(heroes: list[str], keyword: str, accent: str, count: int,
                   category: str, out: Path) -> None:
    """A clickable channel thumbnail without Remotion. ONE striking, text-free hero,
    punched and vignetted, with a bold accent number badge and a punchy keyword seated
    on a scrim + accent underline. Only graphics/comparison videos get the
    VANILLA-vs-MODDED split (it's meaningless for new lands / quests)."""
    heroes = [h for h in heroes if h]
    W, H = SIZE
    acc = _hex(accent)
    canvas = Image.new("RGB", SIZE, (10, 14, 20))
    comparison = category in ("graphics", "comparison") and len(heroes) >= 2
    if comparison:
        left = ImageEnhance.Color(_cover(Image.open(heroes[1]).convert("RGB"),
                                         (W // 2, H))).enhance(0.3)
        right = _punch(_cover(Image.open(heroes[0]).convert("RGB"), (W // 2, H)))
        canvas.paste(left, (0, 0)); canvas.paste(right, (W // 2, 0))
        ImageDraw.Draw(canvas).rectangle([W // 2 - 5, 0, W // 2 + 5, H], fill=accent)
        _tag(ImageDraw.Draw(canvas), "VANILLA", (30, 26), (150, 150, 150))
        _tag(ImageDraw.Draw(canvas), "MODDED", (W // 2 + 30, 26), accent)
    elif heroes:
        canvas.paste(_punch(_cover(Image.open(heroes[0]).convert("RGB"), SIZE)), (0, 0))
        canvas = _vignette(canvas)

    # Scrim: strong bottom gradient + a soft left wash so text is always legible.
    scrim = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim)
    for i in range(340):                            # bottom band for the keyword
        a = int(225 * (i / 340) ** 1.5)
        sd.line([(0, H - 340 + i), (W, H - 340 + i)], fill=(0, 0, 0, a))
    for i in range(460):                            # gentle left wash for depth
        a = int(120 * (1 - i / 460) ** 1.7)
        sd.line([(i, 0), (i, H)], fill=(0, 0, 0, a))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), scrim).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # --- Keyword: huge, white, heavy stroke, with an accent underline bar. ---
    kw = keyword.upper()
    kfont = _font(154 if len(kw) <= 9 else 120)
    kx, ky = 52, H - 205
    kb = draw.textbbox((kx, ky), kw, font=kfont)
    draw.text((kx, ky), kw, font=kfont, fill="white", stroke_width=10,
              stroke_fill="black")
    # accent underline directly under the keyword
    uy = kb[3] + 6
    draw.rounded_rectangle([kx + 4, uy, kb[2], uy + 16], radius=8, fill=acc)
    # channel kicker above the keyword, on its own accent chip
    kick = "SKYRIM MODS"
    kkf = _font(42)
    kkb = draw.textbbox((0, 0), kick, font=kkf)
    kw_w, kw_h = kkb[2] - kkb[0], kkb[3] - kkb[1]
    draw.rounded_rectangle([kx, ky - kw_h - 40, kx + kw_w + 34, ky - 14],
                           radius=12, fill=acc)
    draw.text((kx + 17, ky - kw_h - 34), kick, font=kkf, fill=(12, 12, 12))

    # --- Number badge, top-left: big accent pill with a drop shadow. ---
    if count:
        bfont = _font(150)
        num = f"{count}"
        bb = draw.textbbox((0, 0), num, font=bfont)
        bw, bh = bb[2] - bb[0], bb[3] - bb[1]
        x0, y0 = 40, 34
        pill = [x0, y0, x0 + bw + 60, y0 + bh + 52]
        # shadow
        draw.rounded_rectangle([pill[0] + 8, pill[1] + 10, pill[2] + 8, pill[3] + 10],
                               radius=26, fill=(0, 0, 0))
        draw.rounded_rectangle(pill, radius=26, fill=(0, 0, 0))         # black ring
        draw.rounded_rectangle([pill[0] + 7, pill[1] + 7, pill[2] - 7, pill[3] - 7],
                               radius=20, fill=acc)                      # accent fill
        draw.text((x0 + 30 - bb[0], y0 + 20 - bb[1]), num, font=bfont,
                  fill=(12, 14, 18))

    # Thick accent border frames it against YouTube's white feed.
    draw.rectangle([0, 0, W - 1, H - 1], outline=acc, width=10)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)


def _hex(color: str):
    c = color.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) if len(c) == 6 else (212, 175, 55)


def make_thumbnail_variants(project, accent: str = "#d4af37",
                            category_title: str = "", n: int = 3) -> list[str]:
    """Render N A/B thumbnail variants (different keyword/banner + panel images) into
    work/<slug>/thumbs/. Returns the list of paths. Remotion when available, else PIL."""
    from ..branding import thumbnail_variants_text
    from ..edit.remotion_render import render_thumbnail
    out_dir = Path(project.workdir) / "thumbs"
    out_dir.mkdir(parents=True, exist_ok=True)

    # One CLEAN, well-exposed hero per mod (never a title-card/text splash), then
    # ranked by image quality so the variants use the best-LOOKING scenes — a mod whose
    # whole gallery is dark won't force a muddy thumbnail. Distinct mods = A/B variety.
    heroes = [img for mod in project.mods if (img := _mod_gallery_hero(mod))]
    heroes = sorted(heroes, key=_hero_quality, reverse=True)
    if not heroes:                                  # last resort: any main image
        ranked = sorted(project.mods, key=lambda m: getattr(m, "endorsements", 0),
                        reverse=True)
        heroes = [img for mod in ranked if (img := _mod_main_image(mod))]
    cid = getattr(project, "category_id", "") or ""
    variants = thumbnail_variants_text(category_title or "", n, cid)
    count = len(project.mods)
    paths = []
    from ..config import channel_config as _cc
    brand = _cc().get('channel', {}).get('name', '')
    # Vary BOTH the hero image and the keyword per variant so YouTube's Test & Compare
    # has genuinely different options to pick a winner from.
    kw_pool = [_keyword_for(cid, project)] + [k for _, k, _ in variants if k]
    kw_pool = list(dict.fromkeys([k.upper() for k in kw_pool if k])) or ["MODS"]
    for i, (headline, keyword, banner) in enumerate(variants):
        hero = heroes[i % len(heroes)] if heroes else None
        out = out_dir / f"thumb_v{i+1}.png"
        if hero and render_thumbnail(headline, keyword, banner, [hero], accent, out,
                                     brand=brand, count=count):
            paths.append(str(out))
        elif heroes:
            # PIL fallback (no Remotion): different hero + keyword each variant.
            ordered = heroes[i % len(heroes):] + heroes[:i % len(heroes)]
            _pil_thumbnail(ordered, kw_pool[i % len(kw_pool)], accent, count, cid, out)
            paths.append(str(out))
    return paths
