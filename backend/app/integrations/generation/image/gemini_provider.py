import base64
import logging

import httpx

from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import GenerationProviderNotConfiguredError, GenerationProviderRequestError
from app.integrations.generation.image.base import GeneratedImage, ImageProvider

logger = logging.getLogger("app.integrations.generation.image")

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

_ASPECT_RATIOS = {"1:1": 1.0, "3:4": 0.75, "4:3": 4 / 3, "9:16": 9 / 16, "16:9": 16 / 9}


def _closest_aspect_ratio(width: int, height: int) -> str:
    ratio = width / height if height else 1.0
    return min(_ASPECT_RATIOS, key=lambda key: abs(_ASPECT_RATIOS[key] - ratio))


class GeminiImageProvider(ImageProvider):
    """Real image generation via the Gemini API's Imagen models
    (`{model}:predict`). Selected as the "cloud" IMAGE_PROVIDER once
    GEMINI_API_KEY (or GOOGLE_API_KEY) is set. Any HTTP failure or
    malformed response raises GenerationProviderRequestError — never a
    fabricated image."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(
            available=True,
            provider="gemini",
            mode="production",
            reason=f"Configured with model {self._model}.",
        )

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024) -> GeneratedImage:
        aspect_ratio = _closest_aspect_ratio(width, height)
        url = f"{_API_BASE}/models/{self._model}:predict"
        body = {
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1, "aspectRatio": aspect_ratio},
        }

        logger.info("Gemini image: submitting request to model=%s aspect_ratio=%s", self._model, aspect_ratio)
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, params={"key": self._api_key}, json=body)
        except httpx.RequestError as exc:
            logger.warning("Gemini image: request failed: %s", exc)
            raise GenerationProviderRequestError(f"Could not reach the Gemini API: {exc}") from exc

        if response.status_code != 200:
            logger.warning("Gemini image: request returned status %s", response.status_code)
            raise GenerationProviderRequestError(
                f"Gemini image generation failed ({response.status_code}): {response.text[:300]}"
            )

        payload = response.json()
        predictions = payload.get("predictions") or []
        if not predictions or "bytesBase64Encoded" not in predictions[0]:
            logger.warning("Gemini image: response had no usable prediction data")
            raise GenerationProviderRequestError(
                f"Gemini returned no image data: {str(payload)[:300]}"
            )

        mime_type = predictions[0].get("mimeType", "image/png")
        image_format = mime_type.rsplit("/", 1)[-1] if "/" in mime_type else "png"
        try:
            data = base64.b64decode(predictions[0]["bytesBase64Encoded"])
        except (ValueError, TypeError) as exc:
            logger.warning("Gemini image: response image data could not be decoded: %s", exc)
            raise GenerationProviderRequestError(f"Gemini returned malformed image data: {exc}") from exc

        logger.info("Gemini image: generation succeeded, %d bytes (%s)", len(data), mime_type)
        return GeneratedImage(data=data, format=image_format, content_type=mime_type, width=width, height=height)


def not_configured_reason() -> str:
    return (
        "Gemini image generation is not configured. Set GEMINI_API_KEY (or GOOGLE_API_KEY) "
        "and optionally GEMINI_IMAGE_MODEL in the backend environment, then restart the server."
    )


class UnconfiguredGeminiImageProvider(ImageProvider):
    """Selected when IMAGE_PROVIDER=cloud but no Gemini key is set —
    honestly reports unavailable rather than skipping straight to a
    confusing error only surfaced on generate()."""

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(available=False, provider="gemini", mode="production", reason=not_configured_reason())

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024) -> GeneratedImage:
        raise GenerationProviderNotConfiguredError(not_configured_reason())
