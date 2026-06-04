"""Voice mastering — make the cloned narration sound close-mic'd and broadcast-clean.

F5 reproduces the reference clip's acoustics, so a reference recorded away from the
mic sounds distant/roomy. This applies a podcast-style chain (denoise, rumble cut,
presence + air EQ, compression, normalize) to bring the voice forward and even out
levels. Applied to every narration segment when voice.yaml has `enhance: true`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# Minimal, transparent mastering: just remove sub-bass rumble and set a comfortable,
# consistent level. No EQ colouring or heavy compression (those made it sound harsh /
# "too loud"). Target ~-19 LUFS — a touch quieter than the reference, clean.
_FILTER = (
    "highpass=f=75,"
    "loudnorm=I=-19:TP=-2:LRA=11"
)


def enhance_file(path: Path, ffmpeg: str | None = None) -> None:
    """Master a narration audio file in place."""
    path = Path(path)
    if not path.exists():
        return
    if ffmpeg is None:
        from ..utils.ffmpeg import ffmpeg_path
        ffmpeg = ffmpeg_path()
    tmp = path.with_name(path.stem + "_enh" + path.suffix)
    try:
        subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(path),
                        "-af", _FILTER, str(tmp)], check=True)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
