from app.core.config import get_settings
from app.integrations.generation.audio.base import AudioProvider
from app.integrations.generation.audio.cloud_provider import OpenAICloudTTSProvider, UnconfiguredOpenAITTSProvider
from app.integrations.generation.audio.local_provider import LocalTTSProvider


def get_audio_provider() -> AudioProvider:
    settings = get_settings()
    if settings.tts_provider == "local":
        return LocalTTSProvider()
    if settings.tts_provider == "cloud":
        api_key = settings.openai_api_key
        if not api_key:
            return UnconfiguredOpenAITTSProvider()
        return OpenAICloudTTSProvider(
            api_key=api_key, model=settings.openai_tts_model, default_voice=settings.openai_tts_voice
        )
    raise ValueError(f"Unknown TTS_PROVIDER '{settings.tts_provider}'.")
