"""TTS provider interface + narration orchestration."""
from __future__ import annotations

import abc
from pathlib import Path

from ..models import Script


class TTSProvider(abc.ABC):
    """Render text to an audio file. Implementations set the actual voice."""

    @abc.abstractmethod
    def synth(self, text: str, out_path: Path) -> None:
        """Synthesize `text` to `out_path` (wav or mp3). Raise on failure."""

    def narrate_script(self, script: Script, out_dir: Path) -> Script:
        """Render every segment's narration; fill segment.audio_path + audio_seconds."""
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            from ..config import voice_config
            do_enhance = voice_config().get("enhance", True)
        except Exception:
            do_enhance = True
        for seg in script.segments:
            if not seg.narration.strip():
                continue
            out = out_dir / f"{seg.segment_id}.mp3"
            self.synth(seg.narration, out)
            if do_enhance:               # master to close-mic'd, broadcast level
                from .enhance import enhance_file
                enhance_file(out)
            seg.audio_path = str(out)
            seg.audio_seconds = _audio_duration(out)
        return script


def _audio_duration(path: Path) -> float:
    """Probe duration via ffprobe/ffmpeg; fall back to a words-per-minute estimate."""
    import subprocess

    from ..utils.ffmpeg import ffmpeg_path

    ff = ffmpeg_path()
    ffprobe = ff.replace("ffmpeg", "ffprobe")
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return float(out.stdout.strip())
    except Exception:
        # ffprobe not available — estimate from ffmpeg null-muxer.
        try:
            res = subprocess.run([ff, "-i", str(path), "-f", "null", "-"],
                                 capture_output=True, text=True, timeout=30)
            for line in res.stderr.splitlines()[::-1]:
                if "time=" in line:
                    t = line.split("time=")[1].split(" ")[0]
                    h, m, s = t.split(":")
                    return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            pass
    return 0.0
