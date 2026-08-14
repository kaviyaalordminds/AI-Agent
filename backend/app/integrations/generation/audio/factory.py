from app.core.config import get_settings
from app.integrations.generation.audio.base import AudioProvider
from app.integrations.generation.audio.cloud_provider import CloudTTSProvider
from app.integrations.generation.audio.local_provider import LocalTTSProvider


def get_audio_provider() -> AudioProvider:
    settings = get_settings()
    if settings.tts_provider == "local":
        return LocalTTSProvider()
    if settings.tts_provider == "cloud":
        return CloudTTSProvider()
    raise ValueError(f"Unknown TTS_PROVIDER '{settings.tts_provider}'.")
