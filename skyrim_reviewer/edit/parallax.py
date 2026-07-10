"""Local 2.5D depth-parallax motion — real dimensional movement from a still, on CPU.

The free/local counterpart to the LTX Kaggle path (edit/i2v.py): estimate a depth
map with Depth-Anything-V2-Small, then render a gentle virtual-camera move so near
objects sweep faster than far ones. ~3-4s/clip on 4 CPU cores, no GPU, no token.

Clips are content-addressed (same scheme as i2v.clip_id) and cached under
work/<slug>/i2v/, so re-renders and images shared across shots are only rendered
once — and a LOCAL clip is interchangeable with an LTX clip downstream: ffrender's
_i2v_segment consumes either.

Heavy deps (torch, transformers) are imported lazily so the pipeline only pays for
them when the `local` backend is actually used.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
_depther = None                       # process-wide, loaded once (amortises the ~3s load)


def clip_id(image_path: str) -> str:
    """Content-addressed id for an image (matches edit/i2v.clip_id)."""
    h = hashlib.md5()
    h.update(Path(image_path).read_bytes())
    return "shot_" + h.hexdigest()[:16]


def _get_depther():
    global _depther
    if _depther is None:
        from transformers import pipeline
        _depther = pipeline("depth-estimation",
                            model="depth-anything/Depth-Anything-V2-Small-hf",
                            device=-1)
    return _depther


def render_parallax(image_path: str, out_path: Path, *, width: int = 768,
                    height: int = 512, fps: int = 24, seconds: float = 4.0,
                    max_shift: float = 12.0, seed: int = 0) -> Path:
    """Render one still into a depth-parallax motion clip. `seed` varies the camera
    path so cycled shots in a segment don't all move identically."""
    import numpy as np
    from PIL import Image
    import imageio.v2 as imageio

    n = max(2, round(fps * seconds))
    img = Image.open(image_path).convert("RGB").resize((width, height))
    d = np.asarray(_get_depther()(img)["depth"], dtype=np.float32)
    d = (d - d.min()) / (d.max() - d.min() + 1e-6)     # 0=far, 1=near
    base = np.asarray(img, dtype=np.float32)
    xx, yy = np.meshgrid(np.arange(width), np.arange(height))

    # Vary the move direction per seed (dolly angle) so cycled clips feel distinct.
    import math
    ang = (seed * 47 % 360) * math.pi / 180.0
    dir_x, dir_y = math.cos(ang), math.sin(ang) * 0.4

    frames = []
    for k in range(n):
        ease = 0.5 - 0.5 * math.cos((k / (n - 1)) * math.pi)   # ease-in-out
        cx = (ease - 0.5) * 2 * max_shift * dir_x
        cy = (ease - 0.5) * 2 * max_shift * dir_y
        sx = np.clip(xx + cx * d, 0, width - 1).astype(np.int32)
        sy = np.clip(yy + cy * d, 0, height - 1).astype(np.int32)
        fr = np.clip((base[sy, sx] - 8) * 1.04, 0, 255).astype(np.uint8)
        frames.append(fr)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimwrite(str(out_path), frames, fps=fps, codec="libx264",
                     quality=7, macro_block_size=None, ffmpeg_log_level="error")
    return out_path


def plan_and_generate(project, work_dir: Path, cfg: dict) -> dict[str, str]:
    """Render a parallax clip for each unique mod image used in this video (capped by
    `i2v_max_clips`; 0 = no cap). Returns {image_local_path: clip_path}. On any failure
    returns {} so the renderer cleanly falls back to Ken Burns."""
    cap = int(cfg.get("i2v_max_clips", 0) or 0)
    out_dir = Path(work_dir) / "i2v"

    # Unique images in first-seen order, deduped by content id.
    order: list[str] = []
    img_to_sid: dict[str, str] = {}
    seen: set[str] = set()
    for mod in project.mods:
        for a in (mod.media or []):
            p = a.local_path
            if not (p and Path(p).suffix.lower() in _IMG_EXT and Path(p).exists()):
                continue
            try:
                sid = clip_id(p)
            except Exception:
                continue
            img_to_sid[p] = sid
            if sid not in seen:
                seen.add(sid)
                order.append(p)
    if cap > 0:
        keep = {img_to_sid[p] for p in order[:cap]}
        order = [p for p in order if img_to_sid[p] in keep]
    if not order:
        return {}

    width = int(cfg.get("i2v_width", 768))
    height = int(cfg.get("i2v_height", 512))
    fps = int(cfg.get("i2v_fps", 24))
    seconds = float(cfg.get("i2v_seconds", 4.0))
    max_shift = float(cfg.get("parallax_shift", 12.0))

    print(f"      Rendering {len(order)} depth-parallax clip(s) on CPU (local)...")
    import time
    t0 = time.time()
    result: dict[str, str] = {}
    for i, p in enumerate(order):
        sid = img_to_sid[p]
        out = out_dir / f"{sid}.mp4"
        if not out.exists():
            try:
                render_parallax(p, out, width=width, height=height, fps=fps,
                                seconds=seconds, max_shift=max_shift, seed=i + 1)
            except Exception as exc:
                print(f"      parallax failed for {Path(p).name} ({exc}); skipping.")
                continue
        result[p] = str(out)
    # Fan the clip out to every image path that shares its content id (dedup reuse).
    clips_by_sid = {img_to_sid[p]: c for p, c in result.items()}
    mapping = {p: clips_by_sid[sid] for p, sid in img_to_sid.items()
               if sid in clips_by_sid}
    print(f"      {len(clips_by_sid)} clip(s) in {time.time() - t0:.0f}s "
          f"({len(mapping)} image(s) mapped).")
    return mapping
