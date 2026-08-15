from app.core.config import get_settings
from app.integrations.generation.transcription.base import TranscriptionProvider
from app.integrations.generation.transcription.cloud_provider import (
    OpenAICloudTranscriptionProvider,
    UnconfiguredOpenAITranscriptionProvider,
)
from app.integrations.generation.transcription.local_provider import LocalWhisperProvider


def get_transcription_provider() -> TranscriptionProvider:
    settings = get_settings()
    if settings.transcription_provider == "local":
        return LocalWhisperProvider()
    if settings.transcription_provider == "cloud":
        api_key = settings.openai_api_key
        if not api_key:
            return UnconfiguredOpenAITranscriptionProvider()
        return OpenAICloudTranscriptionProvider(api_key=api_key, model=settings.openai_transcription_model)
    raise ValueError(f"Unknown TRANSCRIPTION_PROVIDER '{settings.transcription_provider}'.")
