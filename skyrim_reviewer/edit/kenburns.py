"""Ken Burns effect (slow zoom + pan) for still images.

Stills are the default visual for mod segments (a screenshot per mod). A static
image for 60-100 seconds is deadly for retention, so we apply a continuous,
gentle zoom/pan so every still feels alive.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from moviepy.editor import ImageClip


def ken_burns_clip(image_path: str, duration: float, size: tuple[int, int],
                   zoom: float = 0.10, fps: int = 30):
    """Return a moviepy clip of `image_path` with a Ken Burns move.

    The image is scaled to cover the frame, then slowly zoomed (and panned in a
    direction chosen deterministically from the filename so adjacent segments
    don't all drift the same way).
    """
    W, H = size
    clip = ImageClip(image_path)

    # Scale so the image fully covers the frame even at the start of the zoom.
    iw, ih = clip.size
    cover = max(W / iw, H / ih) * (1 + zoom)
    clip = clip.resize(cover).set_duration(duration)

    # Pick a pan direction from a hash of the path (stable, varied).
    h = int(hashlib.md5(image_path.encode()).hexdigest(), 16)
    dir_x = (1 if (h & 1) else -1)
    dir_y = (1 if (h & 2) else -1)

    cw, ch = clip.size
    max_dx = max(cw - W, 0)
    max_dy = max(ch - H, 0)

    def position(t):
        frac = t / duration if duration else 0
        # Ease in-out so the motion starts and ends gently.
        ease = frac * frac * (3 - 2 * frac)
        x = -(max_dx / 2) - dir_x * (max_dx / 2) * (ease - 0.5)
        y = -(max_dy / 2) - dir_y * (max_dy / 2) * (ease - 0.5)
        return (x, y)

    # Slow continuous zoom on top of the pan.
    clip = clip.resize(lambda t: 1 + (zoom * 0.5) * (t / duration if duration else 0))
    clip = clip.set_position(position).set_fps(fps)
    return clip


def clip_for_segment(media_paths: list[str], duration: float, size: tuple[int, int],
                     fps: int = 30):
    """Build the visual for one segment.

    - A video file is used directly (trimmed/looped to `duration`).
    - One or more images get Ken Burns; multiple images split the duration evenly.
    """
    from moviepy.editor import CompositeVideoClip, VideoFileClip, concatenate_videoclips

    images = [p for p in media_paths if Path(p).suffix.lower() in
              {".png", ".jpg", ".jpeg", ".webp"}]
    videos = [p for p in media_paths if Path(p).suffix.lower() in
              {".mp4", ".mov", ".mkv", ".webm"}]

    if videos:
        v = VideoFileClip(videos[0]).resize(newsize=size)
        if v.duration >= duration:
            return v.subclip(0, duration)
        # loop the clip to fill the segment
        loops = int(duration // v.duration) + 1
        return concatenate_videoclips([v] * loops).subclip(0, duration)

    if not images:
        from moviepy.editor import ColorClip
        return ColorClip(size, color=(15, 20, 30)).set_duration(duration)

    per = duration / len(images)
    sub = [ken_burns_clip(p, per, size, fps=fps) for p in images]
    track = concatenate_videoclips(
        [CompositeVideoClip([c], size=size) for c in sub], method="compose")
    return track.set_duration(duration)
