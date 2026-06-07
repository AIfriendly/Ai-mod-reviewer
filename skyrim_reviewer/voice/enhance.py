"""Voice mastering — make the cloned narration sound close-mic'd and broadcast-clean.

F5 reproduces the reference clip's acoustics, so a reference recorded away from the
mic sounds distant/roomy. This applies a podcast-style chain (denoise, rumble cut,
presence + air EQ, compression, normalize) to bring the voice forward and even out
levels. Applied to every narration segment when voice.yaml has `enhance: true`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# "Proximity" master — counters the F5 'radio / far from mic' character without the
# harsh, too-loud chain we rejected: add low-mid body (closeness), cut the boxy
# 'telephone' mids, restore presence + air, then a gentle -19 LUFS level. No compressor.
_FILTER = (
    "highpass=f=70,"
    "equalizer=f=130:t=q:w=1.0:g=2.5,"          # body / proximity warmth
    "equalizer=f=450:t=q:w=1.4:g=-2.5,"         # cut boxy 'radio' midrange
    "equalizer=f=5500:t=q:w=2:g=2.5,"           # presence / clarity
    "equalizer=f=11000:t=highshelf:g=3,"        # air (de-dull the bandlimited feel)
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
