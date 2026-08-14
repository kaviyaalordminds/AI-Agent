from app.integrations.capability import CapabilityStatus
from app.integrations.generation.audio.base import AudioProvider, SynthesizedAudio
from app.integrations.generation.errors import GenerationProviderNotConfiguredError

_NOT_CONFIGURED_REASON = (
    "No cloud TTS vendor is configured in this deployment. Cloud TTS is an "
    "architecture point (this class) ready for a real vendor integration "
    "(e.g. ElevenLabs, Azure Speech) — set TTS_PROVIDER=local to use the "
    "local engine instead."
)


class CloudTTSProvider(AudioProvider):
    """Architecture point for a future cloud TTS vendor. Selected via
    TTS_PROVIDER=cloud. No vendor is wired up yet in this deployment —
    every call honestly reports/raises "not configured" rather than
    faking audio output."""

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(
            available=False, provider="cloud", mode="production", reason=_NOT_CONFIGURED_REASON
        )

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language: str | None = None,
        speed: float = 1.0,
        format: str = "wav",
    ) -> SynthesizedAudio:
        raise GenerationProviderNotConfiguredError(_NOT_CONFIGURED_REASON)
