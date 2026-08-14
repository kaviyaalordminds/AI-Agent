from app.core.config import get_settings
from app.integrations.generation.image.base import ImageProvider
from app.integrations.generation.image.gemini_provider import GeminiImageProvider, UnconfiguredGeminiImageProvider
from app.integrations.generation.image.local_provider import LocalImageProvider


def get_image_provider() -> ImageProvider:
    settings = get_settings()
    if settings.image_provider == "local":
        return LocalImageProvider()
    if settings.image_provider == "cloud":
        api_key = settings.resolved_gemini_api_key
        if not api_key:
            return UnconfiguredGeminiImageProvider()
        return GeminiImageProvider(api_key=api_key, model=settings.gemini_image_model)
    raise ValueError(f"Unknown IMAGE_PROVIDER '{settings.image_provider}'.")
