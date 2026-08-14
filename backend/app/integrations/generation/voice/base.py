"""VoiceProvider abstraction (voice cloning) — deliberately separate from
AudioProvider/TTS: cloning a real person's voice carries consent and
misuse risks plain TTS doesn't, so callers must pass an explicit
confirmation and every profile is scoped to the user who created it
(see app/models/voice_profile.py) — never accessible cross-user.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.integrations.capability import CapabilityStatus


@dataclass
class ClonedVoiceProfile:
    provider_ref: str
    """Provider-specific reference to the trained voice model."""


@dataclass
class VoiceSynthesisResult:
    data: bytes
    format: str
    content_type: str


class VoiceProvider(ABC):
    @abstractmethod
    def capability(self) -> CapabilityStatus:
        raise NotImplementedError

    @abstractmethod
    async def clone_voice(self, sample_audio: bytes, consent_confirmed: bool) -> ClonedVoiceProfile:
        """Must raise ValueError if consent_confirmed is False — cloning
        never proceeds without the caller having confirmed permission to
        use the voice. Raises GenerationProviderNotConfiguredError if
        unavailable."""
        raise NotImplementedError

    @abstractmethod
    async def synthesize_with_voice(self, text: str, profile: ClonedVoiceProfile) -> VoiceSynthesisResult:
        raise NotImplementedError
