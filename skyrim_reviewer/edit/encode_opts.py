"""ffmpeg encode settings + small video-config helpers — no moviepy dependency.

Split out of assemble.py so the ffmpeg-native render path (ffrender.py, the
default engine) never has to import moviepy just to read a codec/preset/resolution
setting; assemble.py (the moviepy fallback) uses these too.
"""
from __future__ import annotations

from ..models import Project


def _has_nvenc() -> bool:
    """True only if NVENC actually ENCODES here (a real GPU box) — ffmpeg lists the
    encoder even without a GPU, so we do a tiny throwaway encode to be sure."""
    import subprocess
    from ..utils.ffmpeg import ffmpeg_path
    try:
        r = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1",
             "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except Exception:
        return False


def _encode_opts():
    """Pick (codec, preset, threads, ffmpeg_params). Uses GPU NVENC when available
    (fast on a GPU box); otherwise multi-threaded x264 at a faster preset. Override
    any of these via config/channel.yaml -> video.{codec,preset,threads}."""
    import os
    cfg = channel_video_cfg()
    threads = int(cfg.get("threads", os.cpu_count() or 4))
    codec = cfg.get("codec") or ("h264_nvenc" if _has_nvenc() else "libx264")
    if codec == "h264_nvenc":
        preset = cfg.get("preset_nvenc", "p4")
        extra = ["-rc", "vbr", "-cq", "23", "-b:v", "0", "-pix_fmt", "yuv420p"]
    else:
        preset = cfg.get("preset", "faster")   # x264: was 'medium'; 'faster' ~2x quicker
        extra = ["-crf", str(cfg.get("crf", 21))]
    return codec, preset, threads, extra


def channel_video_cfg() -> dict:
    from ..config import channel_config
    return channel_config()["video"]


def project_resolution(project: Project) -> list[int]:
    from ..config import channel_config
    return channel_config()["video"]["resolution"]


def project_fps(project: Project) -> int:
    from ..config import channel_config
    return channel_config()["video"]["fps"]
