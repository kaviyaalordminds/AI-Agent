"""AudioProvider abstraction (text-to-speech).

Same pattern as every other provider in this codebase: application code
calls this interface, never a TTS engine/binary/vendor SDK directly.
`get_audio_provider()` decides the concrete implementation from
TTS_PROVIDER + AI_RUNTIME_MODE.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.integrations.capability import CapabilityStatus


@dataclass
class SynthesizedAudio:
    data: bytes
    format: str
    content_type: str


class AudioProvider(ABC):
    @abstractmethod
    def capability(self) -> CapabilityStatus:
        """Real, current status — never a cached guess."""
        raise NotImplementedError

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language: str | None = None,
        speed: float = 1.0,
        format: str = "wav",
    ) -> SynthesizedAudio:
        """Raise GenerationProviderNotConfiguredError if unavailable, or
        GenerationProviderRequestError if the engine itself fails —
        never return silently-fabricated audio."""
        raise NotImplementedError
