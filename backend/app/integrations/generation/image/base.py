"""ImageProvider abstraction (text-to-image generation)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.integrations.capability import CapabilityStatus


@dataclass
class GeneratedImage:
    data: bytes
    format: str
    content_type: str
    width: int
    height: int


class ImageProvider(ABC):
    @abstractmethod
    def capability(self) -> CapabilityStatus:
        raise NotImplementedError

    @abstractmethod
    async def generate(self, prompt: str, width: int = 1024, height: int = 1024) -> GeneratedImage:
        """Raise GenerationProviderNotConfiguredError if unavailable, or
        GenerationProviderRequestError if generation itself fails."""
        raise NotImplementedError
