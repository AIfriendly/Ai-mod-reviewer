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
