from app.core.config import get_settings
from app.integrations.generation.video.base import VideoProvider
from app.integrations.generation.video.gemini_provider import GeminiVideoProvider, UnconfiguredGeminiVideoProvider
from app.integrations.generation.video.local_provider import LocalVideoProvider


def get_video_provider() -> VideoProvider:
    settings = get_settings()
    if settings.video_provider == "local":
        return LocalVideoProvider()
    if settings.video_provider == "cloud":
        api_key = settings.resolved_gemini_api_key
        if not api_key:
            return UnconfiguredGeminiVideoProvider()
        return GeminiVideoProvider(
            api_key=api_key,
            model=settings.gemini_video_model,
            max_wait_seconds=settings.generation_max_job_duration_seconds,
        )
    raise ValueError(f"Unknown VIDEO_PROVIDER '{settings.video_provider}'.")
