from app.core.config import get_settings
from app.integrations.generation.transcription.base import TranscriptionProvider
from app.integrations.generation.transcription.cloud_provider import CloudTranscriptionProvider
from app.integrations.generation.transcription.local_provider import LocalWhisperProvider


def get_transcription_provider() -> TranscriptionProvider:
    settings = get_settings()
    if settings.transcription_provider == "local":
        return LocalWhisperProvider()
    if settings.transcription_provider == "cloud":
        return CloudTranscriptionProvider()
    raise ValueError(f"Unknown TRANSCRIPTION_PROVIDER '{settings.transcription_provider}'.")
