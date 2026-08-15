from app.core.config import get_settings
from app.integrations.generation.image.base import ImageProvider
from app.integrations.generation.image.local_provider import LocalImageProvider
from app.integrations.generation.image.openai_provider import OpenAIImageProvider, UnconfiguredOpenAIImageProvider


def get_image_provider() -> ImageProvider:
    settings = get_settings()
    if settings.image_provider == "local":
        return LocalImageProvider()
    if settings.image_provider == "cloud":
        api_key = settings.openai_api_key
        if not api_key:
            return UnconfiguredOpenAIImageProvider()
        return OpenAIImageProvider(api_key=api_key, model=settings.openai_image_model)
    raise ValueError(f"Unknown IMAGE_PROVIDER '{settings.image_provider}'.")
