from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import GenerationProviderNotConfiguredError
from app.integrations.generation.video.base import GeneratedVideo, VideoProvider

_NOT_CONFIGURED_REASON = (
    "No cloud video-generation vendor is configured in this deployment. "
    "This is an architecture point ready for a real vendor integration "
    "(e.g. Runway) — video generation is expected to run asynchronously "
    "via GPU workers or an external provider in production, see the "
    "GenerationJob queue."
)


class CloudVideoProvider(VideoProvider):
    """Architecture point for a future cloud/GPU-worker video-generation
    vendor. Selected via VIDEO_PROVIDER=cloud."""

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(
            available=False, provider="cloud", mode="production", reason=_NOT_CONFIGURED_REASON
        )

    async def generate(self, prompt: str, duration_seconds: float = 4.0) -> GeneratedVideo:
        raise GenerationProviderNotConfiguredError(_NOT_CONFIGURED_REASON)
