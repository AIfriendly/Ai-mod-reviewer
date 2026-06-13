"""Locate an ffmpeg binary.

Prefers a system ffmpeg (faster, full-featured); falls back to the static binary
bundled with imageio-ffmpeg so the pipeline runs even where ffmpeg isn't installed.
"""
from __future__ import annotations

import os
import shutil


def ffmpeg_path() -> str:
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "No ffmpeg found. Install it (apt-get install ffmpeg) or "
            "`pip install imageio-ffmpeg`."
        ) from exc


def ffprobe_path() -> str:
    """Locate ffprobe (sits next to ffmpeg). Falls back to 'ffprobe' on PATH."""
    system = shutil.which("ffprobe")
    if system:
        return system
    ff = ffmpeg_path()
    cand = os.path.join(os.path.dirname(ff), "ffprobe")
    return cand if os.path.exists(cand) else "ffprobe"


def configure_moviepy() -> None:
    """Point moviepy at whichever ffmpeg we resolved."""
    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", ffmpeg_path())
    os.environ.setdefault("FFMPEG_BINARY", ffmpeg_path())
