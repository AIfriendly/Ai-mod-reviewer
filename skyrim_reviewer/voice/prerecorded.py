"""Pre-recorded narration — drop one audio file per segment into a folder.

Use this if you render your cloned voice yourself (e.g. with a local model) and
just want the pipeline to pick up the files. Name them <segment_id>.wav/.mp3.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .base import TTSProvider


class PrerecordedProvider(TTSProvider):
    def __init__(self, cfg: dict):
        self.audio_dir = Path(cfg.get("audio_dir", "work/narration"))

    def synth(self, text: str, out_path: Path) -> None:
        # `text` is ignored; we look up a file matching the target segment id.
        seg_id = out_path.stem
        for ext in (".wav", ".mp3", ".m4a"):
            candidate = self.audio_dir / f"{seg_id}{ext}"
            if candidate.exists():
                if candidate.resolve() != out_path.resolve():
                    shutil.copy(candidate, out_path)
                return
        raise FileNotFoundError(
            f"No pre-recorded audio for segment '{seg_id}' in {self.audio_dir}. "
            f"Expected {seg_id}.wav/.mp3."
        )
