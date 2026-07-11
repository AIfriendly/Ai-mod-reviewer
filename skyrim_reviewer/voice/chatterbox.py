"""Chatterbox voice cloning — runs LOCALLY on this machine's CPU (or GPU if present).

Chatterbox (Resemble AI, MIT) is zero-shot: it clones from ONE reference clip, no
transcript needed (unlike F5). Small enough (~350M-500M params) to run on CPU in a
container with no GPU — measured ~3.7x real-time on 4 cores, so a ~10-minute
episode's narration takes roughly 35-40 minutes to generate. The model weights
download once from HuggingFace on first use.

config/voice.yaml:
    provider: chatterbox
    chatterbox:
      ref_audio: voices/clone/ref_primary.wav
      device: cpu            # or "cuda" if this machine actually has a GPU

For the free-Kaggle-GPU-offload variant instead, see chatterbox_kaggle.py
(provider: chatterbox_kaggle) — same voice tech, much faster, needs a Kaggle token.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .base import TTSProvider
from .kaggle_gpu import _concat_wavs, _split_for_tts


class ChatterboxProvider(TTSProvider):
    def __init__(self, cfg: dict):
        self.ref_audio = cfg.get("ref_audio", "voices/clone/ref_primary.wav")
        self.device = cfg.get("device", "cpu")
        self._model = None

    def _engine(self):
        """Lazily load the model once (~20-30s the first time, incl. HF download)."""
        if self._model is None:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            self._model = ChatterboxTurboTTS.from_pretrained(device=self.device)
        return self._model

    def synth(self, text: str, out_path: Path) -> None:
        import torchaudio as ta
        ref = Path(self.ref_audio)
        if not ref.exists():
            raise FileNotFoundError(
                f"Chatterbox reference audio not found: {ref}. "
                f"Run `skyrim-reviewer voice-prep` to create it.")
        model = self._engine()

        # Chunk defensively (same approach as the F5/Kaggle paths) so a long mod
        # segment can't silently truncate or rush in a single generation call.
        chunks = _split_for_tts(text)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = out_path.parent / f".{out_path.stem}_chunks"
        tmp_dir.mkdir(exist_ok=True)
        parts = []
        for i, chunk in enumerate(chunks):
            wav = model.generate(chunk, audio_prompt_path=str(ref))
            p = tmp_dir / f"{i:02d}.wav"
            ta.save(str(p), wav, model.sr)
            parts.append(p)

        wav_path = out_path.with_suffix(".wav")
        _concat_wavs(parts, wav_path)
        for p in parts:
            p.unlink(missing_ok=True)
        tmp_dir.rmdir()

        if out_path.suffix == ".mp3" and wav_path.exists():
            from ..utils.ffmpeg import ffmpeg_path
            subprocess.run([ffmpeg_path(), "-y", "-i", str(wav_path), str(out_path)],
                           capture_output=True, check=True)
            wav_path.unlink(missing_ok=True)
