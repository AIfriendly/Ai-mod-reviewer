"""Bridge to render the Remotion title card into the project's workdir.

Requires Node + the remotion/ sub-project's deps installed (`npm install` there).
If Remotion or Node isn't available, this is a no-op and the assembler simply
skips the title card — the pipeline still produces a video.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REMOTION_DIR = ROOT / "remotion"


def render_title_card(title: str, subtitle: str, accent: str, out_path: Path) -> bool:
    """Render the TitleCard composition to out_path. Returns True on success."""
    if shutil.which("npx") is None or not (REMOTION_DIR / "node_modules").exists():
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path = out_path.resolve()   # subprocess runs in remotion/, so use an abs path
    props = json.dumps({"title": title, "subtitle": subtitle, "accent": accent})
    try:
        subprocess.run(
            ["npx", "remotion", "render", "src/index.ts", "TitleCard",
             str(out_path), f"--props={props}"],
            cwd=str(REMOTION_DIR), check=True, capture_output=True, text=True,
            timeout=600,
        )
        return out_path.exists()
    except Exception:
        return False


def _vignette(im, strength: float = 0.55):
    """Darken the edges with a soft radial gradient so the central subject pops — the
    cheap, faceless-friendly way to get subject/background separation."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
        w, h = im.size
        mask = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(mask)
        d.ellipse([-w * 0.25, -h * 0.25, w * 1.25, h * 1.25], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=min(w, h) * 0.12))
        dark = Image.new("RGB", (w, h), (0, 0, 0))
        # Blend toward black at the edges by `strength` where the mask is dark.
        faded = Image.composite(im, Image.blend(im, dark, strength), mask)
        return faded
    except Exception:
        return im


def _stage_hero(src: Path, dest: Path) -> bool:
    """Copy a hero image into Remotion's public/ dir, punched up for thumbnail use:
    auto-contrast, lifted shadows on dark shots, richer colour and a touch of sharpening
    so it reads boldly at small sizes instead of looking muddy. Falls back to a plain
    copy if Pillow can't process it."""
    try:
        from PIL import Image, ImageEnhance, ImageOps
        im = Image.open(src).convert("RGB")
        im = ImageOps.autocontrast(im, cutoff=1)
        mean = sum(im.convert("L").resize((32, 32)).getdata()) / 1024
        if mean < 95:                                   # lift dark Skyrim interiors
            im = ImageEnhance.Brightness(im).enhance(1.18)
        im = ImageEnhance.Color(im).enhance(1.30)       # punchier, cinematic colour
        im = ImageEnhance.Contrast(im).enhance(1.14)
        im = ImageEnhance.Sharpness(im).enhance(1.35)
        im = _vignette(im)                              # subject-background separation
        dest = dest.with_suffix(".jpg")
        im.save(dest, quality=92)
        return dest.name
    except Exception:
        try:
            shutil.copyfile(src, dest)
            return dest.name
        except Exception:
            return None


def render_thumbnail(headline: str, keyword: str, banner: str,
                     image_paths: list[str], accent: str, out_path: Path,
                     badge: bool = True, brand: str = "", count: int = 0) -> bool:
    """Render the channel-style Thumbnail still (1280x720). Returns True on success.

    Hero images are staged in remotion/public/ so they load via staticFile().
    """
    if shutil.which("npx") is None or not (REMOTION_DIR / "node_modules").exists():
        return False
    if not image_paths:
        return False
    public = REMOTION_DIR / "public"
    public.mkdir(parents=True, exist_ok=True)
    names = []
    for i, p in enumerate(image_paths[:3]):
        src = Path(p)
        if not src.exists():
            continue
        name = _stage_hero(src, public / f"thumb_{i}")
        if name:
            names.append(name)
    if not names:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path = out_path.resolve()   # subprocess runs in remotion/, so use an abs path
    props = json.dumps({"headline": headline, "keyword": keyword, "banner": banner,
                        "images": names, "accent": accent,
                        "count": count, "brand": brand})
    try:
        subprocess.run(
            ["npx", "remotion", "still", "src/index.ts", "Thumbnail",
             str(out_path), f"--props={props}"],
            cwd=str(REMOTION_DIR), check=True, capture_output=True, text=True,
            timeout=300,
        )
        return out_path.exists()
    except Exception:
        return False
