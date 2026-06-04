"""F5-TTS voice cloning provider.

F5-TTS is zero-shot: it clones from ONE short reference clip (ideally a clean,
≤15s, 24 kHz mono sample) plus that clip's transcript, at synthesis time. There is
no multi-sample "training" in this flow — quality comes from the reference clip and
its transcript, so pick the cleanest sample. Prepare references with
`skyrim-reviewer voice-prep` (resamples + loudness-normalizes).

config/voice.yaml:
    provider: f5tts
    f5tts:
      ref_audio: voices/clone/ref_primary.wav
      ref_text: ""          # leave empty to auto-transcribe the reference (Whisper)
      model: F5TTS_v1_Base  # F5-TTS model id
      speed: 1.0            # <1 slower / more deliberate

Runs on CPU (slow) or GPU (fast). The model weights download once from HuggingFace.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .base import TTSProvider


def _ensure_ffmpeg_on_path() -> None:
    """F5/Whisper's audio loading shells out to a system `ffmpeg`. If there isn't one,
    expose the bundled imageio-ffmpeg binary under the name `ffmpeg` on PATH."""
    if shutil.which("ffmpeg"):
        return
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        bindir = Path(exe).parent / "_ffbin"
        bindir.mkdir(exist_ok=True)
        link = bindir / "ffmpeg"
        if not link.exists():
            try:
                link.symlink_to(exe)
            except Exception:
                shutil.copy(exe, link)
        os.environ["PATH"] = str(bindir) + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


class F5TTSProvider(TTSProvider):
    def __init__(self, cfg: dict):
        self.ref_audio = cfg.get("ref_audio", "voices/clone/ref_primary.wav")
        self.ref_text = cfg.get("ref_text", "")          # "" -> auto-transcribe
        self.model = cfg.get("model", "F5TTS_v1_Base")
        self.speed = float(cfg.get("speed", 1.0))
        self.seed = cfg.get("seed", None)
        self.nfe_step = int(cfg.get("nfe_step", 32))   # lower = faster (CPU), default 32
        self._api = None

    def _engine(self):
        """Lazily build the F5-TTS API object (loads the model once)."""
        if self._api is None:
            _ensure_ffmpeg_on_path()
            from f5_tts.api import F5TTS
            self._api = F5TTS(model=self.model)
        return self._api

    def synth(self, text: str, out_path: Path) -> None:
        ref = Path(self.ref_audio)
        if not ref.exists():
            raise FileNotFoundError(
                f"F5-TTS reference audio not found: {ref}. "
                f"Run `skyrim-reviewer voice-prep` to create it.")
        wav_path = out_path.with_suffix(".wav")
        wav_path.parent.mkdir(parents=True, exist_ok=True)

        api = self._engine()
        api.infer(
            ref_file=str(ref),
            ref_text=self.ref_text or "",     # empty -> F5 auto-transcribes the ref
            gen_text=text,
            file_wave=str(wav_path),
            speed=self.speed,
            seed=self.seed,
            nfe_step=self.nfe_step,
            remove_silence=True,
        )

        # The pipeline asks for .mp3 segments; transcode the F5 wav if needed.
        if out_path.suffix == ".mp3" and wav_path.exists():
            from ..utils.ffmpeg import ffmpeg_path
            subprocess.run([ffmpeg_path(), "-y", "-i", str(wav_path), str(out_path)],
                           capture_output=True, check=True)
