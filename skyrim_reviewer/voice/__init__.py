"""Pluggable text-to-speech. Your cloned voice plugs in via config/voice.yaml.

    provider: elevenlabs | openai | piper | f5tts | chatterbox | kaggle | prerecorded
"""
from __future__ import annotations

from ..config import voice_config
from .base import TTSProvider


def get_provider(cfg: dict | None = None) -> TTSProvider:
    cfg = cfg or voice_config()
    provider = cfg.get("provider", "elevenlabs")
    if provider == "elevenlabs":
        from .elevenlabs import ElevenLabsProvider
        return ElevenLabsProvider(cfg.get("elevenlabs", {}))
    if provider == "openai":
        from .openai_tts import OpenAITTSProvider
        return OpenAITTSProvider(cfg.get("openai", {}))
    if provider == "piper":
        from .piper import PiperProvider
        return PiperProvider(cfg.get("piper", {}))
    if provider == "f5tts":
        from .f5tts import F5TTSProvider
        return F5TTSProvider(cfg.get("f5tts", {}))
    if provider == "kaggle":
        from .kaggle_gpu import KaggleF5Provider
        # Reuse the f5tts ref/nfe settings unless a kaggle block overrides them.
        return KaggleF5Provider({**cfg.get("f5tts", {}), **cfg.get("kaggle", {})})
    if provider == "chatterbox":
        from .chatterbox_kaggle import KaggleChatterboxProvider
        return KaggleChatterboxProvider(cfg.get("chatterbox", {}))
    if provider == "prerecorded":
        from .prerecorded import PrerecordedProvider
        return PrerecordedProvider(cfg.get("prerecorded", {}))
    raise ValueError(f"Unknown TTS provider: {provider}")


__all__ = ["TTSProvider", "get_provider"]
