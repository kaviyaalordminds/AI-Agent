from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import GenerationProviderNotConfiguredError
from app.integrations.generation.transcription.base import TranscriptionProvider, TranscriptionResult

_NOT_CONFIGURED_REASON = (
    "No cloud transcription vendor is configured in this deployment. This "
    "is an architecture point ready for a real vendor integration — set "
    "TRANSCRIPTION_PROVIDER=local to use a local Whisper backend instead."
)


class CloudTranscriptionProvider(TranscriptionProvider):
    """Architecture point for a future cloud transcription vendor.
    Selected via TRANSCRIPTION_PROVIDER=cloud."""

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(
            available=False, provider="cloud", mode="production", reason=_NOT_CONFIGURED_REASON
        )

    async def transcribe(self, audio_data: bytes, language: str | None = None) -> TranscriptionResult:
        raise GenerationProviderNotConfiguredError(_NOT_CONFIGURED_REASON)
