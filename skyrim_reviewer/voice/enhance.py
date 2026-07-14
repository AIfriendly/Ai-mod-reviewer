"""Voice mastering — make the cloned narration sound close-mic'd and broadcast-clean.

A TTS clone reproduces the reference clip's acoustics, so this applies a podcast-style
EQ/level chain to bring the voice forward and even out levels. Applied to every
narration segment when voice.yaml has `enhance: true`. The chain is selected by
`enhance_preset` in voice.yaml (default "proximity"):

  proximity — original F5-oriented master: body + presence, gentle -19 LUFS.
  bright    — crisper, air-forward master for Chatterbox: upsamples for headroom,
              lifts presence, and runs a harmonic exciter to synthesise "air" above
              the model's 12 kHz output ceiling, then a hotter -16 LUFS.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# "Proximity" master — add low-mid body (closeness), cut the boxy 'telephone' mids,
# restore presence + air, then a gentle -19 LUFS level. No compressor.
_PROXIMITY = (
    "highpass=f=70,"
    "equalizer=f=130:t=q:w=1.0:g=2.5,"          # body / proximity warmth
    "equalizer=f=450:t=q:w=1.4:g=-2.5,"         # cut boxy 'radio' midrange
    "equalizer=f=5500:t=q:w=2:g=2.5,"           # presence / clarity
    "treble=g=3:f=11000,"                        # air shelf (de-dull bandlimited feel)
    "loudnorm=I=-19:TP=-2:LRA=11"
)

# "Bright" master — crisper, air-forward. Chatterbox outputs at 24 kHz (hard 12 kHz
# ceiling); resample to 48 kHz for headroom, lift presence, then aexciter synthesises
# upper harmonics to add the "air" the bandlimit removed, plus a strong air shelf.
_BRIGHT = (
    "aresample=48000,"
    "highpass=f=65,"
    "equalizer=f=240:t=q:w=1.1:g=1.0,"          # slight warmth
    "equalizer=f=3200:t=q:w=1.5:g=2.5,"         # diction / presence
    "aexciter=amount=2:freq=6500:ceil=16000:blend=3,"   # synthesise air > 12 kHz
    "treble=g=6:f=8000,"                         # strong air shelf
    "loudnorm=I=-16:TP=-1.5:LRA=11"
)

# "Clarity" — an aggressive de-muffle (user-approved). Chatterbox output is dark, so
# this pushes presence + a strong harmonic exciter and air shelf to bring the voice
# right forward and kill the muffled quality, at a hotter -15 LUFS.
_CLARITY = (
    "aresample=48000,"
    "highpass=f=60,"
    "equalizer=f=2800:t=q:w=1.3:g=3.5,"         # presence / diction
    "equalizer=f=6000:t=q:w=1.4:g=3,"           # clarity
    "aexciter=amount=5:freq=5000:ceil=17000:blend=5,"   # strong synthesised air
    "treble=g=9:f=6500,"                         # big air shelf
    "loudnorm=I=-15:TP=-1.5:LRA=11"
)

# "Warm" — user-approved. Clear and present WITHOUT the harshness of "clarity": adds
# low-mid body, a moderate presence lift, a gentle de-ess notch at ~7 kHz to kill
# sibilance, a light exciter and a soft air shelf, at a comfortable -16 LUFS. This is
# the default narration master.
_WARM = (
    "aresample=48000,"
    "highpass=f=75,"
    "equalizer=f=200:t=q:w=1.0:g=2,"            # low-mid body / warmth
    "equalizer=f=3000:t=q:w=1.4:g=2.5,"         # presence / diction (moderate)
    "equalizer=f=7200:t=q:w=2:g=-2,"            # de-ess: tame harsh sibilance
    "aexciter=amount=2:freq=6000:ceil=15000:blend=2.5,"  # gentle synthesised air
    "treble=g=3.5:f=9000,"                       # soft air shelf (not the harsh g=9)
    "loudnorm=I=-16:TP=-1.5:LRA=11"
)

_PRESETS = {"proximity": _PROXIMITY, "bright": _BRIGHT, "clarity": _CLARITY,
            "warm": _WARM}


def enhance_file(path: Path, ffmpeg: str | None = None, preset: str | None = None) -> None:
    """Master a narration audio file in place. `preset` defaults to voice.yaml's
    `enhance_preset` (then "proximity") so every provider's call site honours it
    without change."""
    path = Path(path)
    if not path.exists():
        return
    if preset is None:
        try:
            from ..config import voice_config
            preset = voice_config().get("enhance_preset", "proximity")
        except Exception:
            preset = "proximity"
    chain = _PRESETS.get(preset, _PROXIMITY)
    if ffmpeg is None:
        from ..utils.ffmpeg import ffmpeg_path
        ffmpeg = ffmpeg_path()
    tmp = path.with_name(path.stem + "_enh" + path.suffix)
    try:
        subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(path),
                        "-af", chain, str(tmp)], check=True)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
