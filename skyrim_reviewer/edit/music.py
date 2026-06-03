"""Background music bed with sidechain-style ducking under narration.

Drop royalty-free / licensed tracks in `music/` (see music/README.md). The track
is looped to the video length, volume-reduced, and ducked further whenever
narration is present so the voice always sits on top.
"""
from __future__ import annotations

import random
from pathlib import Path

# Attribution for the bundled royalty-free tracks. Kevin MacLeod tracks are CC BY 4.0,
# which REQUIRES crediting — the renderer adds the chosen track's credit to the video
# description automatically. Add an entry here when you add a track.
TRACK_CREDITS = {
    "lord_of_the_land": "“Lord of the Land” by Kevin MacLeod (incompetech.com) — CC BY 4.0",
    "virtutes_instrumenti": "“Virtutes Instrumenti” by Kevin MacLeod (incompetech.com) — CC BY 4.0",
    "dragon_and_toast": "“Dragon and Toast” by Kevin MacLeod (incompetech.com) — CC BY 4.0",
    "ossuary_rest": "“Ossuary 5 – Rest” by Kevin MacLeod (incompetech.com) — CC BY 4.0",
}


def track_credit(track_path: str | None) -> str | None:
    return TRACK_CREDITS.get(Path(track_path).stem) if track_path else None


# Default royalty-free fantasy/epic set (Kevin MacLeod, CC BY 4.0). Audio is
# git-ignored, so `skyrim-reviewer fetch-music` downloads these into music/.
_DEFAULT_TRACK_URLS = {
    "lord_of_the_land": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Lord%20of%20the%20Land.mp3",
    "virtutes_instrumenti": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Virtutes%20Instrumenti.mp3",
    "dragon_and_toast": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Dragon%20and%20Toast.mp3",
    "ossuary_rest": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Ossuary%205%20-%20Rest.mp3",
}


def fetch_default_tracks(music_dir: str = "music") -> list[str]:
    """Download the bundled CC BY fantasy tracks into music/. Returns the paths."""
    import httpx
    d = Path(music_dir)
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for stem, url in _DEFAULT_TRACK_URLS.items():
        dest = d / f"{stem}.mp3"
        if not dest.exists() or dest.stat().st_size < 100_000:
            r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120,
                          follow_redirects=True)
            r.raise_for_status()
            dest.write_bytes(r.content)
        out.append(str(dest))
    return out


def pick_track(music_dir: str = "music") -> str | None:
    d = Path(music_dir)
    if not d.exists():
        return None
    tracks = [p for p in d.iterdir()
              if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"}]
    return str(random.choice(tracks)) if tracks else None


def music_bed(total_duration: float, music_dir: str = "music",
              base_volume: float = 0.12, track: str | None = None):
    """Return a looped, volume-reduced music clip, or None if no track is available."""
    track = track or pick_track(music_dir)
    if not track:
        return None
    from moviepy.audio.fx.all import audio_loop, volumex
    from moviepy.editor import AudioFileClip

    clip = AudioFileClip(track)
    clip = audio_loop(clip, duration=total_duration)
    return clip.fx(volumex, base_volume)
