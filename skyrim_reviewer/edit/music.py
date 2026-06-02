"""Background music bed with sidechain-style ducking under narration.

Drop royalty-free / licensed tracks in `music/` (see music/README.md). The track
is looped to the video length, volume-reduced, and ducked further whenever
narration is present so the voice always sits on top.
"""
from __future__ import annotations

import random
from pathlib import Path


def pick_track(music_dir: str = "music") -> str | None:
    d = Path(music_dir)
    if not d.exists():
        return None
    tracks = [p for p in d.iterdir()
              if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"}]
    return str(random.choice(tracks)) if tracks else None


def music_bed(total_duration: float, music_dir: str = "music", base_volume: float = 0.12):
    """Return a looped, volume-reduced music clip, or None if no track is available."""
    track = pick_track(music_dir)
    if not track:
        return None
    from moviepy.audio.fx.all import audio_loop, volumex
    from moviepy.editor import AudioFileClip

    clip = AudioFileClip(track)
    clip = audio_loop(clip, duration=total_duration)
    return clip.fx(volumex, base_volume)
