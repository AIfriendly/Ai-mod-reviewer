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


# A single ffmpeg command chaining more than ~this many sequential acrossfade
# filters reliably deadlocks ffmpeg's filter-graph scheduler (all input decoder
# threads block on futex_wait, zero CPU progress, no output growth) — confirmed at
# 20 chained crossfades for a ~35 min video; every prior video stayed under 11 min
# (≤~7 segments) and never hit this. Batch the chain instead of growing it unbounded.
_MAX_CHAIN = 6


def _crossfade_chain(inputs: list[tuple[str, float, float]], out_path, xfade: float,
                     fade_in: bool) -> bool:
    """One ffmpeg call chaining len(inputs) segments with acrossfade. `inputs` is
    [(track_path, seek_offset, duration), ...]. Returns True on success."""
    import subprocess
    from ..utils.ffmpeg import ffmpeg_path
    n = len(inputs)
    args = [ffmpeg_path(), "-y", "-v", "error"]
    for t, off, seg_seconds in inputs:
        args += ["-ss", f"{off:.1f}", "-t", f"{seg_seconds:.1f}", "-i", t]
    fc = ("[0:a]afade=t=in:d=1.5[a0];" if fade_in else "[0:a]anull[a0];")
    for i in range(1, n):
        fc += f"[{i}:a]anull[a{i}];"
    if n == 1:
        fc += "[a0]anull[out]"
    else:
        prev = "[a0]"
        for i in range(1, n):
            outl = "[out]" if i == n - 1 else f"[c{i}]"
            fc += f"{prev}[a{i}]acrossfade=d={xfade}:c1=tri:c2=tri{outl};"
            prev = outl
    args += ["-filter_complex", fc, "-map", "[out]", str(out_path)]
    try:
        subprocess.run(args, check=True, capture_output=True, text=True, timeout=300)
        return True
    except Exception:
        return False


def build_music_bed(total_dur: float, out_path, music_dir: str = "music",
                    seg_seconds: float = 105.0, xfade: float = 3.0):
    """Stitch MULTIPLE tracks into one bed that ROTATES across the video (crossfading
    every ~seg_seconds) instead of looping a single track. Returns (bed_path, [stems])
    for crediting, or (None, []) if there are no tracks.

    Built in batches of at most `_MAX_CHAIN` crossfades per ffmpeg call (long videos
    need many more segments than that fit safely in one filter graph — see
    `_MAX_CHAIN`), then the batch files are themselves crossfaded together the same
    way. Batch count is always small (a batch of batches), so this never regresses
    into the same deep-chain problem regardless of total video length."""
    import subprocess
    import tempfile
    from pathlib import Path
    from ..utils.ffmpeg import ffmpeg_path
    d = Path(music_dir)
    tracks = sorted(str(p) for p in d.iterdir()
                    if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"}) \
        if d.exists() else []
    if not tracks:
        return None, []
    if len(tracks) == 1:                       # nothing to rotate through
        return tracks[0], [Path(tracks[0]).stem]
    step = max(30.0, seg_seconds - xfade)
    n = max(2, int(total_dur // step) + 1)

    def _duration(path: str) -> float:
        import re
        r = subprocess.run([ffmpeg_path(), "-i", path], capture_output=True, text=True)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", r.stderr or "")
        return (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
               if m else seg_seconds)

    track_durations = {t: _duration(t) for t in tracks}
    used = []
    segments = []                # (track, offset, seg_seconds)
    for i in range(n):
        t = tracks[i % len(tracks)]
        used.append(Path(t).stem)
        # Vary which part of the track each pass, but WRAP within that track's own
        # real length — an unwrapped offset eventually seeks past a shorter track's
        # end (e.g. a 105s step against a 186s track after just 2 rotations), which
        # starves the crossfade filter of samples it's waiting on and hangs ffmpeg
        # indefinitely rather than erroring.
        safe_span = max(track_durations[t] - seg_seconds, 1.0)
        off = ((i // len(tracks)) * seg_seconds) % safe_span
        segments.append((t, off, seg_seconds))

    seen, stems = set(), []
    for s in used:
        if s not in seen:
            seen.add(s); stems.append(s)

    try:
        with tempfile.TemporaryDirectory(dir=Path(out_path).parent) as tmp:
            tmp = Path(tmp)
            batches = [segments[i:i + _MAX_CHAIN]
                      for i in range(0, len(segments), _MAX_CHAIN)]
            batch_files = []
            for bi, batch in enumerate(batches):
                bf = tmp / f"batch_{bi}.m4a"
                if not _crossfade_chain(batch, bf, xfade, fade_in=(bi == 0)):
                    raise RuntimeError("batch crossfade failed")
                batch_files.append(str(bf))
            if len(batch_files) == 1:
                final_src = batch_files[0]
            else:
                # Crossfade the (few) batch outputs together — same mechanism, but
                # the batch count is always small so this chain never grows unbounded.
                merged = tmp / "merged.m4a"
                # Each batch file's own duration varies (last one is shorter) — feed
                # whole files rather than fixed seg_seconds slices.
                # -t longer than the file just clamps to EOF, so a fixed large value
                # works for every batch regardless of its actual (varying) length.
                merge_inputs = [(bf, 0.0, 1e9) for bf in batch_files]
                if not _crossfade_chain(merge_inputs, merged, xfade, fade_in=False):
                    raise RuntimeError("batch merge crossfade failed")
                final_src = str(merged)
            subprocess.run(
                [ffmpeg_path(), "-y", "-v", "error", "-i", final_src,
                 "-t", f"{total_dur + 1:.1f}", "-c", "copy", str(out_path)],
                check=True, capture_output=True, text=True, timeout=120)
        return str(out_path), stems
    except Exception:
        return tracks[0], [Path(tracks[0]).stem]   # fall back to a single track


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
