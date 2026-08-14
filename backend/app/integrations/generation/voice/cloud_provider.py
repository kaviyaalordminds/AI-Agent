from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import GenerationProviderNotConfiguredError
from app.integrations.generation.voice.base import ClonedVoiceProfile, VoiceProvider, VoiceSynthesisResult

_NOT_CONFIGURED_REASON = (
    "No cloud voice-cloning vendor is configured in this deployment. This "
    "is an architecture point ready for a real vendor integration (e.g. "
    "ElevenLabs) — set VOICE_PROVIDER=local to attempt local cloning instead."
)


class CloudVoiceProvider(VoiceProvider):
    """Architecture point for a future cloud voice-cloning vendor.
    Selected via VOICE_PROVIDER=cloud."""

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(
            available=False, provider="cloud", mode="production", reason=_NOT_CONFIGURED_REASON
        )

    async def clone_voice(self, sample_audio: bytes, consent_confirmed: bool) -> ClonedVoiceProfile:
        if not consent_confirmed:
            raise ValueError(
                "Voice cloning requires explicit confirmation that you have "
                "permission to use this voice."
            )
        raise GenerationProviderNotConfiguredError(_NOT_CONFIGURED_REASON)

    async def synthesize_with_voice(self, text: str, profile: ClonedVoiceProfile) -> VoiceSynthesisResult:
        raise GenerationProviderNotConfiguredError(_NOT_CONFIGURED_REASON)
