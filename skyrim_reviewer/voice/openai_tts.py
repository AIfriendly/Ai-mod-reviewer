"""OpenAI TTS provider (optional alternative to the cloned voice)."""
from __future__ import annotations

from pathlib import Path

from ..config import require_env
from .base import TTSProvider


class OpenAITTSProvider(TTSProvider):
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def synth(self, text: str, out_path: Path) -> None:
        from openai import OpenAI

        client = OpenAI(api_key=require_env("OPENAI_API_KEY"))
        with client.audio.speech.with_streaming_response.create(
            model=self.cfg.get("model", "gpt-4o-mini-tts"),
            voice=self.cfg.get("voice", "onyx"),
            input=text,
        ) as resp:
            resp.stream_to_file(out_path)
