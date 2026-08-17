"""ImageProvider abstraction (text-to-image generation and image
editing/enhancement)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import GenerationProviderRequestError


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

    async def enhance(
        self, image: bytes, image_content_type: str, prompt: str, width: int = 1024, height: int = 1024
    ) -> GeneratedImage:
        """Edits/enhances an existing image. Not every ImageProvider
        implementation supports this (deliberately NOT abstract, so
        existing/future providers and test fakes that only implement
        generate() keep working unchanged) — the default raises a clean,
        structured error instead of an AttributeError. Concrete providers
        that support editing (OpenAI) override this. Raise
        GenerationProviderNotConfiguredError if unavailable, or
        GenerationProviderRequestError if enhancement itself fails."""
        raise GenerationProviderRequestError(f"{self.capability().provider} does not support image enhancement.")
