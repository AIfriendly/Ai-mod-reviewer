"""Qwen3-TTS voice cloning — runs LOCALLY (open-weight, HuggingFace), zero-shot.

ICL ("in-context learning") mode: the reference clip is passed straight into the
generation call, no separate enrollment/training step, no cloud account needed.
Without a transcript it falls back to x-vector-only cloning (lower fidelity, no
text required) — same "no transcript needed" default as chatterbox.py. Give it a
transcript (ref_text, or a `<ref_audio>.txt` sidecar) for the full ICL mode.

config/voice.yaml:
    provider: qwen
    qwen:
      ref_audio: voices/clone/ref_primary.wav
      ref_text: ""                              # optional; enables full ICL mode
      model: Qwen/Qwen3-TTS-12Hz-1.7B-Base
      device: cpu                                # "cuda:0" if this machine has a GPU
      language: English

No GPU here means this is CPU inference on a 1.7B model — expect it to be slow
(similar order of magnitude to F5-TTS/Chatterbox on CPU). Weights download once
from HuggingFace on first use.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .base import TTSProvider
from .kaggle_gpu import _concat_wavs, _split_for_tts


class QwenTTSProvider(TTSProvider):
    def __init__(self, cfg: dict):
        self.ref_audio = cfg.get("ref_audio", "voices/clone/ref_primary.wav")
        sidecar = Path(self.ref_audio).with_suffix(".txt")
        self.ref_text = (cfg.get("ref_text", "") or
                         (sidecar.read_text(encoding="utf-8").strip()
                          if sidecar.exists() else ""))
        self.model_id = cfg.get("model", "Qwen/Qwen3-TTS-12Hz-1.7B-Base")
        self.device = cfg.get("device", "cpu")
        self.language = cfg.get("language", "English")
        self._model = None

    def _engine(self):
        """Lazily load the model once (downloads weights on first use)."""
        if self._model is None:
            import torch
            from qwen_tts import Qwen3TTSModel
            # bfloat16 needs a GPU (or a recent CPU with native bf16 support) to be
            # fast/stable — float32 is the safe default off a GPU.
            dtype = torch.bfloat16 if self.device.startswith("cuda") else torch.float32
            self._model = Qwen3TTSModel.from_pretrained(
                self.model_id, device_map=self.device, dtype=dtype)
        return self._model

    def synth(self, text: str, out_path: Path) -> None:
        import soundfile as sf
        ref = Path(self.ref_audio)
        if not ref.exists():
            raise FileNotFoundError(
                f"Qwen TTS reference audio not found: {ref}. "
                f"Run `skyrim-reviewer voice-prep` to create it.")
        model = self._engine()

        # Chunk defensively (same approach as the F5/Chatterbox paths) so a long mod
        # segment can't silently truncate or rush in a single generation call.
        chunks = _split_for_tts(text)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = out_path.parent / f".{out_path.stem}_chunks"
        tmp_dir.mkdir(exist_ok=True)
        parts = []
        for i, chunk in enumerate(chunks):
            kwargs = dict(text=chunk, language=self.language, ref_audio=str(ref))
            if self.ref_text:
                kwargs["ref_text"] = self.ref_text          # full ICL: text + audio
            else:
                kwargs["x_vector_only_mode"] = True          # audio only, no transcript
            wavs, sr = model.generate_voice_clone(**kwargs)
            p = tmp_dir / f"{i:02d}.wav"
            sf.write(str(p), wavs[0], sr)
            parts.append(p)

        wav_path = out_path.with_suffix(".wav")
        _concat_wavs(parts, wav_path)
        for p in parts:
            p.unlink(missing_ok=True)
        tmp_dir.rmdir()

        if out_path.suffix == ".mp3" and wav_path.exists():
            from .base import wav_to_mp3
            wav_to_mp3(wav_path, out_path)
