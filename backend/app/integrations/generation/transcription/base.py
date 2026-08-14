"""TranscriptionProvider abstraction (speech-to-text)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.integrations.capability import CapabilityStatus


@dataclass
class TranscriptionSegment:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass
class TranscriptionResult:
    text: str
    language: str | None
    segments: list[TranscriptionSegment] = field(default_factory=list)


class TranscriptionProvider(ABC):
    @abstractmethod
    def capability(self) -> CapabilityStatus:
        raise NotImplementedError

    @abstractmethod
    async def transcribe(self, audio_data: bytes, language: str | None = None) -> TranscriptionResult:
        """Raise GenerationProviderNotConfiguredError if unavailable, or
        GenerationProviderRequestError if transcription itself fails."""
        raise NotImplementedError
