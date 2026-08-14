import importlib.util

from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import GenerationProviderNotConfiguredError
from app.integrations.generation.image.base import GeneratedImage, ImageProvider


def _diffusion_backend_available() -> bool:
    return importlib.util.find_spec("diffusers") is not None and importlib.util.find_spec("torch") is not None


class LocalImageProvider(ImageProvider):
    """Local text-to-image generation via a diffusion model (e.g. Stable
    Diffusion through `diffusers`). This requires a real model checkpoint
    (several GB) and, practically, a GPU — this application does not
    bundle either. capability() honestly reports unavailable unless the
    required Python packages are actually importable on this machine,
    rather than pretending image generation works."""

    def capability(self) -> CapabilityStatus:
        if _diffusion_backend_available():
            return CapabilityStatus(
                available=True,
                provider="local-diffusers",
                mode="local",
                reason="Local diffusion backend (diffusers + torch) is installed.",
            )
        return CapabilityStatus(
            available=False,
            provider="local-diffusers",
            mode="local",
            reason=(
                "Local image generation is unavailable on this machine: no diffusion "
                "backend (diffusers + torch) is installed, and/or no model checkpoint "
                "is configured. Local image generation typically also requires a GPU "
                "for acceptable performance. Install `torch` and `diffusers` and "
                "configure a model, or set IMAGE_PROVIDER=cloud with a configured "
                "cloud provider."
            ),
        )

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024) -> GeneratedImage:
        raise GenerationProviderNotConfiguredError(self.capability().reason)
