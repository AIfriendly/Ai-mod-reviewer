"""ElevenLabs TTS — use this for YOUR cloned voice.

Create a cloned voice in the ElevenLabs dashboard, then set its voice_id in
config/voice.yaml (or the ELEVENLABS_VOICE_ID env var). The cloned voice IS the
channel narrator.
"""
from __future__ import annotations

from pathlib import Path

from ..config import get_env, require_env
from .base import TTSProvider


class ElevenLabsProvider(TTSProvider):
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.voice_id = cfg.get("voice_id") or get_env("ELEVENLABS_VOICE_ID")
        if not self.voice_id:
            raise RuntimeError(
                "No ElevenLabs voice_id. Set it in config/voice.yaml or "
                "ELEVENLABS_VOICE_ID — this is your cloned voice."
            )

    def synth(self, text: str, out_path: Path) -> None:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=require_env("ELEVENLABS_API_KEY"))
        audio = client.text_to_speech.convert(
            voice_id=self.voice_id,
            model_id=self.cfg.get("model", "eleven_multilingual_v2"),
            output_format=self.cfg.get("output_format", "mp3_44100_128"),
            text=text,
            voice_settings={
                "stability": self.cfg.get("stability", 0.45),
                "similarity_boost": self.cfg.get("similarity_boost", 0.8),
                "style": self.cfg.get("style", 0.0),
            },
        )
        with open(out_path, "wb") as fh:
            for chunk in audio:
                if chunk:
                    fh.write(chunk)
