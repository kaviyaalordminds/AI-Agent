from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import GenerationProviderNotConfiguredError
from app.integrations.generation.voice.base import ClonedVoiceProfile, VoiceProvider, VoiceSynthesisResult

_REASON = (
    "Local voice cloning is unavailable on this machine: no local voice-cloning "
    "model is installed (this typically requires a GPU and a dedicated model such "
    "as a real-time voice conversion checkpoint, which this application does not "
    "bundle). Set VOICE_PROVIDER=cloud with a configured cloud provider."
)


class LocalVoiceProvider(VoiceProvider):
    """Architecture point for local voice cloning. Honestly unavailable in
    this deployment — see module docstring reason."""

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(available=False, provider="local", mode="local", reason=_REASON)

    async def clone_voice(self, sample_audio: bytes, consent_confirmed: bool) -> ClonedVoiceProfile:
        if not consent_confirmed:
            raise ValueError(
                "Voice cloning requires explicit confirmation that you have "
                "permission to use this voice."
            )
        raise GenerationProviderNotConfiguredError(_REASON)

    async def synthesize_with_voice(self, text: str, profile: ClonedVoiceProfile) -> VoiceSynthesisResult:
        raise GenerationProviderNotConfiguredError(_REASON)
