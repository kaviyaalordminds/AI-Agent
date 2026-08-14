from app.core.config import get_settings
from app.integrations.generation.image.base import ImageProvider
from app.integrations.generation.image.cloud_provider import CloudImageProvider
from app.integrations.generation.image.local_provider import LocalImageProvider


def get_image_provider() -> ImageProvider:
    settings = get_settings()
    if settings.image_provider == "local":
        return LocalImageProvider()
    if settings.image_provider == "cloud":
        return CloudImageProvider()
    raise ValueError(f"Unknown IMAGE_PROVIDER '{settings.image_provider}'.")
