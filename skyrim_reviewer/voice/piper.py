"""Piper TTS — local, offline, free. Good zero-cost default for testing."""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

from .base import TTSProvider


class PiperProvider(TTSProvider):
    def __init__(self, cfg: dict):
        self.model_path = cfg.get("model_path", "voices/en_US-ryan-high.onnx")

    def synth(self, text: str, out_path: Path) -> None:
        # Piper writes wav; if the caller asked for .mp3 we still write a .wav twin.
        wav_path = out_path.with_suffix(".wav")
        try:
            from piper.voice import PiperVoice

            voice = PiperVoice.load(self.model_path)
            with wave.open(str(wav_path), "wb") as wf:
                voice.synthesize(text, wf)
        except ImportError:
            # Fall back to the piper CLI if the python package isn't installed.
            subprocess.run(
                ["piper", "--model", self.model_path, "--output_file", str(wav_path)],
                input=text, text=True, check=True,
            )
        if out_path.suffix == ".mp3" and wav_path.exists():
            from ..utils.ffmpeg import ffmpeg_path
            subprocess.run([ffmpeg_path(), "-y", "-i", str(wav_path), str(out_path)],
                           capture_output=True, check=True)
