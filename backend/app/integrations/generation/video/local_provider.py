import shutil

from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import GenerationProviderNotConfiguredError
from app.integrations.generation.video.base import GeneratedVideo, VideoProvider


class LocalVideoProvider(VideoProvider):
    """Local AI video generation is not something any open, CPU-only,
    no-GPU environment can realistically do — genuine text/image-to-video
    models require a GPU and multi-GB checkpoints this application does
    not bundle. capability() always honestly reports unavailable locally
    (ffmpeg presence alone does not make AI video generation possible —
    ffmpeg only encodes/transcodes, it doesn't generate content) rather
    than pretending a local run would work."""

    def capability(self) -> CapabilityStatus:
        ffmpeg_present = shutil.which("ffmpeg") is not None
        detail = (
            "ffmpeg is installed (usable for encoding once a video generation "
            "backend exists) but " if ffmpeg_present else ""
        )
        return CapabilityStatus(
            available=False,
            provider="local",
            mode="local",
            reason=(
                f"Local video generation is unavailable on this machine. {detail}"
                "no local AI video generation backend is installed — this typically "
                "requires a GPU and a multi-GB model checkpoint. Set VIDEO_PROVIDER=cloud "
                "with a configured cloud provider (e.g. Runway) for video generation."
            ),
        )

    async def generate(
        self, prompt: str, duration_seconds: float = 4.0, reference_image: bytes | None = None
    ) -> GeneratedVideo:
        raise GenerationProviderNotConfiguredError(self.capability().reason)
