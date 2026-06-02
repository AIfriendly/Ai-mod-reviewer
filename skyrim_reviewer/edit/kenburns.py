"""Ken Burns effect (slow zoom + pan) for still images — with MULTI-SHOT support.

Footage policy for this channel: fully automated, using the single main image the
NexusMods API legally exposes per mod. One static still over a 60s segment kills
retention, so we synthesize several DISTINCT shots from that one image (different
crops, zoom directions and focus points) and hard-cut between them. The result
feels like b-roll even though it's one screenshot.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from moviepy.editor import ImageClip


def _seed(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest(), 16)


# A set of distinct "camera moves" — each is (zoom_from, zoom_to, focus_x, focus_y,
# pan_dx, pan_dy). focus_* in [0,1] choose which part of the image to frame.
_MOVES = [
    (1.00, 1.12, 0.30, 0.40, 1, 0),    # push in, framed left, drift right
    (1.14, 1.02, 0.70, 0.45, -1, 0),   # pull out from the right
    (1.05, 1.16, 0.50, 0.30, 0, 1),    # push in on the top third, drift down
    (1.12, 1.00, 0.45, 0.70, 0, -1),   # pull out from the bottom
    (1.02, 1.14, 0.65, 0.60, -1, -1),  # diagonal push
    (1.15, 1.04, 0.35, 0.35, 1, 1),    # diagonal pull
]


def _shot(image_path: str, duration: float, size: tuple[int, int], move, fps: int):
    """One Ken Burns shot of `image_path` using a single camera move."""
    W, H = size
    z_from, z_to, fx, fy, dx, dy = move

    clip = ImageClip(image_path)
    iw, ih = clip.size
    # Cover the frame with headroom for the largest zoom and the pan.
    cover = max(W / iw, H / ih) * (max(z_from, z_to) + 0.06)
    clip = clip.resize(cover).set_duration(duration)
    cw, ch = clip.size

    max_dx = max(cw - W, 0)
    max_dy = max(ch - H, 0)
    # Base position frames the chosen focus point of the image.
    base_x = -max_dx * fx
    base_y = -max_dy * fy
    pan_x = (max_dx * 0.18) * dx
    pan_y = (max_dy * 0.18) * dy

    def position(t):
        frac = (t / duration) if duration else 0
        ease = frac * frac * (3 - 2 * frac)        # smoothstep
        return (base_x - pan_x * (ease - 0.5),
                base_y - pan_y * (ease - 0.5))

    def zoom(t):
        frac = (t / duration) if duration else 0
        return z_from + (z_to - z_from) * frac

    return clip.resize(zoom).set_position(position).set_fps(fps)


def multi_shot_clip(image_path: str, duration: float, size: tuple[int, int],
                    fps: int = 30, shot_seconds: float = 18.0):
    """Turn ONE image into several distinct Ken Burns shots, hard-cut together."""
    from moviepy.editor import CompositeVideoClip, concatenate_videoclips

    n = max(1, round(duration / shot_seconds))
    n = min(n, len(_MOVES))
    per = duration / n
    start = _seed(image_path) % len(_MOVES)

    shots = []
    for i in range(n):
        move = _MOVES[(start + i * 2) % len(_MOVES)]   # step by 2 for variety
        shot = _shot(image_path, per, size, move, fps)
        shots.append(CompositeVideoClip([shot], size=size).set_duration(per))
    return concatenate_videoclips(shots, method="compose").set_duration(duration)


# Backwards-compatible single-shot helper.
def ken_burns_clip(image_path: str, duration: float, size: tuple[int, int],
                   zoom: float = 0.10, fps: int = 30):
    move = _MOVES[_seed(image_path) % len(_MOVES)]
    from moviepy.editor import CompositeVideoClip
    return CompositeVideoClip([_shot(image_path, duration, size, move, fps)],
                              size=size).set_duration(duration)


def clip_for_segment(media_paths: list[str], duration: float, size: tuple[int, int],
                     fps: int = 30, shot_seconds: float = 18.0):
    """Build the visual for one segment.

    - A video file (e.g. an author-permitted clip) is used directly.
    - A single image gets MULTI-SHOT Ken Burns (several moves from one still).
    - Multiple images split the duration and each gets its own move.
    """
    from moviepy.editor import (ColorClip, CompositeVideoClip, VideoFileClip,
                                concatenate_videoclips)

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
    sub = [ken_burns_clip(p, per, size, fps=fps) for p in images]
    return concatenate_videoclips(
        [CompositeVideoClip([c], size=size) for c in sub],
        method="compose").set_duration(duration)
