from app.core.config import get_settings
from app.integrations.generation.voice.base import VoiceProvider
from app.integrations.generation.voice.cloud_provider import CloudVoiceProvider
from app.integrations.generation.voice.local_provider import LocalVoiceProvider


def get_voice_provider() -> VoiceProvider:
    settings = get_settings()
    if settings.voice_provider == "local":
        return LocalVoiceProvider()
    if settings.voice_provider == "cloud":
        return CloudVoiceProvider()
    raise ValueError(f"Unknown VOICE_PROVIDER '{settings.voice_provider}'.")
