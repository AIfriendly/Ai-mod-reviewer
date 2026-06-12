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
        dest = public / f"thumb_{i}{src.suffix.lower()}"
        shutil.copyfile(src, dest)
        names.append(dest.name)
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
