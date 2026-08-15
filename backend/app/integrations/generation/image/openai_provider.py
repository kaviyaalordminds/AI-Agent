import base64
import logging

import httpx

from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import GenerationProviderNotConfiguredError, GenerationProviderRequestError
from app.integrations.generation.image.base import GeneratedImage, ImageProvider

logger = logging.getLogger("app.integrations.generation.image")

_API_URL = "https://api.openai.com/v1/images/generations"

# gpt-image-* models don't support response_format (always return
# b64_json) and use a different size set than dall-e-2/3.
_GPT_IMAGE_SIZES = ["1024x1024", "1536x1024", "1024x1536"]
_DALLE_SIZES = ["1024x1024", "1792x1024", "1024x1792"]


def _closest_size(width: int, height: int, sizes: list[str]) -> str:
    target_ratio = width / height if height else 1.0

    def ratio_of(size: str) -> float:
        w, h = (int(part) for part in size.split("x"))
        return w / h

    return min(sizes, key=lambda size: abs(ratio_of(size) - target_ratio))


class OpenAIImageProvider(ImageProvider):
    """Real image generation via the OpenAI Images API
    (`POST /v1/images/generations`). Selected as the "cloud" IMAGE_PROVIDER
    once OPENAI_API_KEY is set. Any HTTP failure or malformed response
    raises GenerationProviderRequestError — never a fabricated image."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(
            available=True,
            provider="openai",
            mode="production",
            reason=f"Configured with model {self._model}.",
        )

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024) -> GeneratedImage:
        is_gpt_image = self._model.startswith("gpt-image")
        size = _closest_size(width, height, _GPT_IMAGE_SIZES if is_gpt_image else _DALLE_SIZES)

        body = {"model": self._model, "prompt": prompt, "size": size, "n": 1}
        if not is_gpt_image:
            # gpt-image-* always returns b64_json and rejects this field;
            # dall-e-2/3 default to a URL response unless asked otherwise.
            body["response_format"] = "b64_json"
        headers = {"Authorization": f"Bearer {self._api_key}"}

        logger.info("OpenAI image: submitting request to model=%s size=%s", self._model, size)
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(_API_URL, json=body, headers=headers)
        except httpx.RequestError as exc:
            logger.warning("OpenAI image: request failed: %s", exc)
            raise GenerationProviderRequestError(f"Could not reach the OpenAI API: {exc}") from exc

        if response.status_code != 200:
            logger.warning("OpenAI image: request returned status %s", response.status_code)
            raise GenerationProviderRequestError(
                f"OpenAI image generation failed ({response.status_code}): {response.text[:300]}"
            )

        payload = response.json()
        results = payload.get("data") or []
        if not results or "b64_json" not in results[0]:
            logger.warning("OpenAI image: response had no usable image data")
            raise GenerationProviderRequestError(f"OpenAI returned no image data: {str(payload)[:300]}")

        try:
            data = base64.b64decode(results[0]["b64_json"])
        except (ValueError, TypeError) as exc:
            logger.warning("OpenAI image: response image data could not be decoded: %s", exc)
            raise GenerationProviderRequestError(f"OpenAI returned malformed image data: {exc}") from exc

        actual_width, actual_height = (int(part) for part in size.split("x"))
        logger.info("OpenAI image: generation succeeded, %d bytes (%s)", len(data), size)
        return GeneratedImage(
            data=data, format="png", content_type="image/png", width=actual_width, height=actual_height
        )


def not_configured_reason() -> str:
    return (
        "OpenAI image generation is not configured. Set OPENAI_API_KEY "
        "and optionally OPENAI_IMAGE_MODEL in the backend environment, then restart the server."
    )


class UnconfiguredOpenAIImageProvider(ImageProvider):
    """Selected when IMAGE_PROVIDER=cloud but no OpenAI key is set —
    honestly reports unavailable rather than skipping straight to a
    confusing error only surfaced on generate()."""

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(available=False, provider="openai", mode="production", reason=not_configured_reason())

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024) -> GeneratedImage:
        raise GenerationProviderNotConfiguredError(not_configured_reason())
