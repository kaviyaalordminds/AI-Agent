from app.core.config import get_settings
from app.integrations.generation.video.base import VideoProvider
from app.integrations.generation.video.cloud_provider import CloudVideoProvider
from app.integrations.generation.video.local_provider import LocalVideoProvider


def get_video_provider() -> VideoProvider:
    settings = get_settings()
    if settings.video_provider == "local":
        return LocalVideoProvider()
    if settings.video_provider == "cloud":
        return CloudVideoProvider()
    raise ValueError(f"Unknown VIDEO_PROVIDER '{settings.video_provider}'.")
