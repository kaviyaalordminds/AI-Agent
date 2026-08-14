from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import GenerationProviderNotConfiguredError
from app.integrations.generation.image.base import GeneratedImage, ImageProvider

_NOT_CONFIGURED_REASON = (
    "No cloud image-generation vendor is configured in this deployment. "
    "This is an architecture point ready for a real vendor integration "
    "(e.g. OpenAI Images, Stability AI) — set IMAGE_PROVIDER=local to "
    "attempt local generation instead."
)


class CloudImageProvider(ImageProvider):
    """Architecture point for a future cloud image-generation vendor.
    Selected via IMAGE_PROVIDER=cloud."""

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(
            available=False, provider="cloud", mode="production", reason=_NOT_CONFIGURED_REASON
        )

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024) -> GeneratedImage:
        raise GenerationProviderNotConfiguredError(_NOT_CONFIGURED_REASON)
