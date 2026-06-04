"""Voice mastering — make the cloned narration sound close-mic'd and broadcast-clean.

F5 reproduces the reference clip's acoustics, so a reference recorded away from the
mic sounds distant/roomy. This applies a podcast-style chain (denoise, rumble cut,
presence + air EQ, compression, normalize) to bring the voice forward and even out
levels. Applied to every narration segment when voice.yaml has `enhance: true`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# Denoise -> rumble/harshness cleanup -> de-mud + presence + air -> compress -> normalize.
_FILTER = (
    "afftdn=nf=-25,"
    "highpass=f=90,lowpass=f=12000,"
    "equalizer=f=250:t=q:w=1.2:g=-3,"      # cut boxy/muddy lows
    "equalizer=f=3200:t=q:w=2:g=4.5,"      # presence — brings voice 'forward'
    "equalizer=f=8000:t=q:w=2:g=2.5,"      # air/clarity
    "acompressor=threshold=-21dB:ratio=3.5:attack=5:release=90:makeup=5,"
    "loudnorm=I=-16:TP=-1.5:LRA=11"
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
