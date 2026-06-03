"""Ken Burns visuals for still images — FIT (never crop) over a blurred fill.

Footage policy: fully automated, using the mod images the NexusMods API exposes.
Earlier versions cover-cropped + zoomed hard, which chopped tall/wide screenshots
and felt "too close". This version always shows the WHOLE image, centered and
fitted, on a softly blurred + darkened fill of the same image, with a gentle zoom.
Multiple images per mod are cycled through; a single image is split into a couple
of gentle push/pull shots so it still has motion.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from . import pil_compat  # noqa: F401  (restores PIL.Image.ANTIALIAS for MoviePy 1.x)
from moviepy.editor import ImageClip


def _seed(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest(), 16)


# Documentary Ken Burns moves: (zoom_from, zoom_to, pan_x, pan_y).
# pan_* = fraction of the frame the camera drifts across the shot (left/right/up/down),
# so the camera glides over the image like a History-Channel doc, not just a static zoom.
_MOVES = [
    (1.06, 1.14,  0.07,  0.00),   # slow push-in, pan right
    (1.14, 1.06, -0.07,  0.00),   # pull-out, pan left
    (1.06, 1.12,  0.00,  0.06),   # push-in, pan down
    (1.12, 1.06,  0.00, -0.06),   # pull-out, pan up
    (1.05, 1.13,  0.06, -0.04),   # push-in, drift up-right
    (1.13, 1.05, -0.06,  0.04),   # pull-out, drift down-left
]


def _blurred_fill(image_path: str, size: tuple[int, int],
                  blur: int = 45, darken: float = 0.5) -> np.ndarray:
    """A cover-cropped, blurred, darkened version of the image that fills the frame
    so the fitted foreground never sits on hard black bars."""
    W, H = size
    im = Image.open(image_path).convert("RGB")
    iw, ih = im.size
    scale = max(W / iw, H / ih)
    im = im.resize((max(int(iw * scale) + 1, W), max(int(ih * scale) + 1, H)),
                   Image.LANCZOS)
    left = (im.width - W) // 2
    top = (im.height - H) // 2
    im = im.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(blur))
    return (np.asarray(im).astype(float) * darken).astype("uint8")


def _shot(image_path: str, duration: float, size: tuple[int, int], move, fps: int):
    """One cinematic shot: the whole image fitted over its blurred fill, with a
    combined zoom + pan (left/right/up/down) so the camera glides across it."""
    from moviepy.editor import CompositeVideoClip

    W, H = size
    z_from, z_to, pan_x, pan_y = move

    bg = ImageClip(_blurred_fill(image_path, size)).set_duration(duration)

    fg = ImageClip(image_path).set_duration(duration)
    iw, ih = fg.size
    fit = min(W / iw, H / ih)                 # fit the whole image into the frame
    fw, fh = fit * iw, fit * ih

    def ease(t):
        f = (t / duration) if duration else 0.0
        return f * f * (3 - 2 * f)            # smoothstep for a slow, weighted glide

    def zoom(t):
        return fit * (z_from + (z_to - z_from) * ease(t))

    def pos(t):
        z = z_from + (z_to - z_from) * ease(t)
        cw, ch = fw * z, fh * z               # current foreground size
        # center, then drift across the frame (pan), measured from mid-shot.
        x = (W - cw) / 2 + pan_x * W * (ease(t) - 0.5)
        y = (H - ch) / 2 + pan_y * H * (ease(t) - 0.5)
        return x, y

    fg = fg.resize(zoom).set_position(pos)
    return (CompositeVideoClip([bg, fg], size=size)
            .set_duration(duration).set_fps(fps))


def multi_shot_clip(image_path: str, duration: float, size: tuple[int, int],
                    fps: int = 30, shot_seconds: float = 18.0):
    """One image -> a couple of gentle push/pull shots so it isn't static."""
    from moviepy.editor import concatenate_videoclips

    n = max(1, min(round(duration / shot_seconds), 3))
    per = duration / n
    start = _seed(image_path) % len(_MOVES)
    shots = [_shot(image_path, per, size, _MOVES[(start + i) % len(_MOVES)], fps)
             for i in range(n)]
    if len(shots) == 1:
        return shots[0]
    return concatenate_videoclips(shots, method="compose").set_duration(duration)


def ken_burns_clip(image_path: str, duration: float, size: tuple[int, int],
                   zoom: float = 0.05, fps: int = 30):
    return _shot(image_path, duration, size, _MOVES[_seed(image_path) % len(_MOVES)], fps)


def clip_for_segment(media_paths: list[str], duration: float, size: tuple[int, int],
                     fps: int = 30, shot_seconds: float = 18.0):
    """Build the visual for one segment.

    - A video file (author-permitted clip) is used directly.
    - Multiple images split the duration; each is fitted over its blurred fill.
    - A single image gets a couple of gentle push/pull shots.
    """
    from moviepy.editor import (ColorClip, VideoFileClip, concatenate_videoclips)

    images = [p for p in media_paths if Path(p).suffix.lower() in
              {".png", ".jpg", ".jpeg", ".webp"}]
    videos = [p for p in media_paths if Path(p).suffix.lower() in
              {".mp4", ".mov", ".mkv", ".webm"}]

    if videos:
        v = VideoFileClip(videos[0]).resize(newsize=size)
        if v.duration >= duration:
            return v.subclip(0, duration)
        loops = int(duration // v.duration) + 1
        return concatenate_videoclips([v] * loops).subclip(0, duration)

    if not images:
        return ColorClip(size, color=(15, 20, 30)).set_duration(duration)

    if len(images) == 1:
        return multi_shot_clip(images[0], duration, size, fps=fps,
                               shot_seconds=shot_seconds)

    per = duration / len(images)
    shots = [_shot(p, per, size, _MOVES[i % len(_MOVES)], fps)
             for i, p in enumerate(images)]
    return concatenate_videoclips(shots, method="compose").set_duration(duration)
