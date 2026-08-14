"""VideoProvider abstraction (text/image-to-video generation)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.integrations.capability import CapabilityStatus


@dataclass
class GeneratedVideo:
    data: bytes
    format: str
    content_type: str
    duration_seconds: float


class VideoProvider(ABC):
    @abstractmethod
    def capability(self) -> CapabilityStatus:
        raise NotImplementedError

    @abstractmethod
    async def generate(
        self, prompt: str, duration_seconds: float = 4.0, reference_image: bytes | None = None
    ) -> GeneratedVideo:
        """`reference_image` enables image-to-video for providers that
        support it (ignored by providers that don't). Raise
        GenerationProviderNotConfiguredError if unavailable, or
        GenerationProviderRequestError if generation itself fails. Video
        generation is resource-intensive — do not assume one machine can
        handle unlimited concurrent jobs (see GenerationJob queue)."""
        raise NotImplementedError
