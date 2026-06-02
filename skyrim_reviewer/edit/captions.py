"""Caption / chapter helpers.

We generate a simple .srt subtitle (one cue per segment) and a YouTube chapter
list computed from the REAL audio durations, so timestamps are accurate.
"""
from __future__ import annotations

from pathlib import Path

from ..models import Script


def _ts(seconds: float, sep: str = ",") -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def segment_durations(script: Script, pause: float = 0.45) -> list[float]:
    """Per-segment on-screen duration = narration audio + a small tail pause."""
    out = []
    for seg in script.segments:
        out.append((seg.audio_seconds or seg.target_seconds or 3.0) + pause)
    return out


def write_srt(script: Script, durations: list[float], out_path: Path) -> None:
    lines, t = [], 0.0
    for i, (seg, dur) in enumerate(zip(script.segments, durations), 1):
        start, end = t, t + dur
        lines += [str(i), f"{_ts(start)} --> {_ts(end)}", seg.narration.strip(), ""]
        t = end
    out_path.write_text("\n".join(lines), encoding="utf-8")


def youtube_chapters(script: Script, durations: list[float]) -> list[str]:
    """'0:00 Intro' style chapter list for the description."""
    out, t = [], 0.0
    for seg, dur in zip(script.segments, durations):
        m, s = int(t // 60), int(t % 60)
        out.append(f"{m}:{s:02d} {seg.title}")
        t += dur
    return out
