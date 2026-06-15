"""Tiny synthesized sound effects (no external assets needed).

A short 'whoosh' transition sting is generated once with ffmpeg's lavfi noise source
and reused. We then build a single SFX track with one whoosh placed at each mod's
on-screen reveal, mixed under the narration so each countdown entry gets an audible
pattern interrupt.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _ff() -> str:
    from ..utils.ffmpeg import ffmpeg_path
    return ffmpeg_path()


def _run(args: list[str]):
    subprocess.run(args, check=True, capture_output=True, text=True)


def make_whoosh(out: Path, dur: float = 0.45) -> Path:
    """Synthesize a soft whoosh: band-passed pink noise with a fast swell + decay."""
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    af = (f"highpass=f=250,lowpass=f=5500,"
          f"afade=t=in:st=0:d={dur*0.45:.3f}:curve=ipar,"
          f"afade=t=out:st={dur*0.45:.3f}:d={dur*0.55:.3f}:curve=qsin,"
          f"volume=0.35,aformat=channel_layouts=stereo:sample_rates=44100")
    _run([_ff(), "-y", "-v", "error", "-f", "lavfi", "-t", f"{dur:.3f}",
          "-i", "anoisesrc=color=pink:amplitude=0.7", "-af", af, str(out)])
    return out


def make_riser(out: Path, dur: float = 3.5) -> Path:
    """Synthesize a build-up 'riser': pink noise that swells from near-silence to a peak,
    opening up its top end — placed so it crests right as the #1 pick is revealed."""
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    af = (f"highpass=f=300,"
          f"volume='0.5*pow(min(t/{dur:.3f},1),3)':eval=frame,"
          f"afade=t=out:st={dur-0.15:.3f}:d=0.15,"
          f"aformat=channel_layouts=stereo:sample_rates=44100")
    _run([_ff(), "-y", "-v", "error", "-f", "lavfi", "-t", f"{dur:.3f}",
          "-i", "anoisesrc=color=pink:amplitude=0.8", "-af", af, str(out)])
    return out


def build_sfx_track(starts: list[float], total: float, out: Path,
                    whoosh: Path | None = None, riser_end: float | None = None,
                    riser_dur: float = 3.5) -> Path | None:
    """Render a full-length silent track with a whoosh at each start time (seconds) and,
    optionally, a build-up riser that crests at `riser_end` (the #1 reveal). Returns the
    track path, or None if there are no cues."""
    if not starts and riser_end is None:
        return None
    wh = whoosh or make_whoosh(out.parent / "whoosh.wav")
    args = [_ff(), "-y", "-v", "error"]
    delays = []
    for st in starts:
        args += ["-i", str(wh)]
        delays.append(max(0, int(st * 1000)))
    riser_idx = None
    if riser_end is not None:
        riser = make_riser(out.parent / "riser.wav", riser_dur)
        riser_idx = len(delays)
        args += ["-i", str(riser)]
        delays.append(max(0, int((riser_end - riser_dur) * 1000)))
    n = len(delays)
    parts = [f"[{i}:a]adelay={ms}|{ms}[d{i}];" for i, ms in enumerate(delays)]
    mix = "".join(f"[d{i}]" for i in range(n))
    chain = ("".join(parts) + mix +
             f"amix=inputs={n}:duration=longest:normalize=0,"
             f"apad,atrim=0:{total:.3f},aformat=channel_layouts=stereo:"
             f"sample_rates=44100[sfx]")
    args += ["-filter_complex", chain, "-map", "[sfx]", str(out)]
    _run(args)
    return out
