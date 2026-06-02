"""Render a lower-third credit strip with Pillow (no ImageMagick dependency).

Shows the mod name + author so every featured mod is credited ON SCREEN, as the
NexusMods terms and r/skyrimmods norms require.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def render_lower_third(name: str, author: str, size: tuple[int, int],
                       out_path: Path, accent: str = "#d4af37") -> str:
    W, H = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        big = ImageFont.truetype("DejaVuSans-Bold.ttf", 46)
        small = ImageFont.truetype("DejaVuSans.ttf", 30)
    except Exception:
        big = small = ImageFont.load_default()

    bar_h = 120
    y0 = H - bar_h - 60
    # translucent backing bar
    draw.rectangle([60, y0, int(W * 0.62), y0 + bar_h], fill=(10, 16, 24, 200))
    draw.rectangle([60, y0, 70, y0 + bar_h], fill=accent)
    draw.text((90, y0 + 18), name, fill=(255, 255, 255, 255), font=big)
    draw.text((90, y0 + 74), f"by {author}", fill=(200, 200, 200, 255), font=small)
    img.save(out_path)
    return str(out_path)
