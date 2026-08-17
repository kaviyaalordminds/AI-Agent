import base64
import logging

import httpx

from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import (
    GenerationProviderNotConfiguredError,
    GenerationProviderRequestError,
    GenerationProviderUnavailableError,
    classify_http_error,
)
from app.integrations.generation.image.base import GeneratedImage, ImageProvider

logger = logging.getLogger("app.integrations.generation.image")

_API_URL = "https://api.openai.com/v1/images/generations"
_EDIT_API_URL = "https://api.openai.com/v1/images/edits"

# gpt-image-* models use a different supported size set than dall-e-2/3.
_GPT_IMAGE_SIZES = ["1024x1024", "1536x1024", "1024x1536"]
_DALLE_SIZES = ["1024x1024", "1792x1024", "1024x1792"]

# dall-e-3 has no edits/enhancement endpoint support at all (OpenAI only
# offers image editing for gpt-image-* and dall-e-2) — checked up front so
# an incompatible OPENAI_IMAGE_MODEL produces one clear, actionable error
# instead of a confusing 400 from the vendor.
_EDIT_INCOMPATIBLE_MODELS = {"dall-e-3"}


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

    def __init__(self, api_key: str, model: str, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self._model = model
        # Injectable only for tests (httpx.MockTransport) — production
        # code never sets this, so httpx.AsyncClient uses its normal
        # network transport.
        self._transport = transport

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

        # No response_format field: current OpenAI API versions reject it
        # outright ("Unknown parameter: 'response_format'") for at least
        # some models/accounts, and every model returns a usable image one
        # way or another without it — gpt-image-* always returns
        # b64_json, dall-e-2/3 return a url — so the response is parsed
        # generically below rather than requested in one specific shape.
        body = {"model": self._model, "prompt": prompt, "size": size, "n": 1}
        headers = {"Authorization": f"Bearer {self._api_key}"}

        logger.info("OpenAI image: submitting request to model=%s size=%s", self._model, size)
        try:
            async with httpx.AsyncClient(timeout=120.0, transport=self._transport) as client:
                response = await client.post(_API_URL, json=body, headers=headers)
        except httpx.RequestError as exc:
            logger.warning("OpenAI image: request failed: %s", exc)
            raise GenerationProviderUnavailableError(f"Could not reach the OpenAI API: {exc}") from exc

        if response.status_code != 200:
            logger.warning("OpenAI image: request returned status %s", response.status_code)
            error_cls = classify_http_error(response.status_code, response.text)
            raise error_cls(
                f"OpenAI image generation failed ({response.status_code}): {response.text[:300]}"
            )

        payload = response.json()
        data = await self._extract_image_bytes(payload)

        actual_width, actual_height = (int(part) for part in size.split("x"))
        logger.info("OpenAI image: generation succeeded, %d bytes (%s)", len(data), size)
        return GeneratedImage(
            data=data, format="png", content_type="image/png", width=actual_width, height=actual_height
        )

    async def enhance(
        self, image: bytes, image_content_type: str, prompt: str, width: int = 1024, height: int = 1024
    ) -> GeneratedImage:
        """Real image editing/enhancement via the OpenAI Images API
        (`POST /v1/images/edits`) — takes the caller's uploaded image plus
        an enhancement instruction and returns a new, actually-edited
        image. Distinct from generate(): this is image-to-image, not
        text-to-image, and uses OpenAI's edits endpoint (multipart image
        upload), which only gpt-image-* and dall-e-2 support."""
        if self._model in _EDIT_INCOMPATIBLE_MODELS:
            raise GenerationProviderRequestError(
                f"The configured OpenAI image model '{self._model}' does not support image "
                "editing/enhancement. Set OPENAI_IMAGE_MODEL to 'gpt-image-1' or 'dall-e-2' "
                "in the backend environment to enable Image Enhancement, then restart the server."
            )

        is_gpt_image = self._model.startswith("gpt-image")
        size = _closest_size(width, height, _GPT_IMAGE_SIZES if is_gpt_image else _DALLE_SIZES)
        extension = (image_content_type.split("/")[-1] or "png").lower()
        if extension == "jpg":
            extension = "jpeg"

        headers = {"Authorization": f"Bearer {self._api_key}"}
        form_data = {"model": self._model, "prompt": prompt, "size": size, "n": "1"}
        files = {"image": (f"image.{extension}", image, image_content_type or "image/png")}

        logger.info("OpenAI image edit: submitting request to model=%s size=%s", self._model, size)
        try:
            async with httpx.AsyncClient(timeout=120.0, transport=self._transport) as client:
                response = await client.post(_EDIT_API_URL, data=form_data, files=files, headers=headers)
        except httpx.RequestError as exc:
            logger.warning("OpenAI image edit: request failed: %s", exc)
            raise GenerationProviderUnavailableError(f"Could not reach the OpenAI API: {exc}") from exc

        if response.status_code != 200:
            logger.warning("OpenAI image edit: request returned status %s", response.status_code)
            error_cls = classify_http_error(response.status_code, response.text)
            raise error_cls(
                f"OpenAI image enhancement failed ({response.status_code}): {response.text[:300]}"
            )

        payload = response.json()
        data = await self._extract_image_bytes(payload)

        actual_width, actual_height = (int(part) for part in size.split("x"))
        logger.info("OpenAI image edit: enhancement succeeded, %d bytes (%s)", len(data), size)
        return GeneratedImage(
            data=data, format="png", content_type="image/png", width=actual_width, height=actual_height
        )

    async def _extract_image_bytes(self, payload: dict) -> bytes:
        results = payload.get("data") or []
        if not results:
            logger.warning("OpenAI image: response had no usable image data")
            raise GenerationProviderRequestError(f"OpenAI returned no image data: {str(payload)[:300]}")

        result = results[0]
        if "b64_json" in result:
            try:
                return base64.b64decode(result["b64_json"])
            except (ValueError, TypeError) as exc:
                logger.warning("OpenAI image: response image data could not be decoded: %s", exc)
                raise GenerationProviderRequestError(f"OpenAI returned malformed image data: {exc}") from exc
        if "url" in result:
            return await self._download(result["url"])
        logger.warning("OpenAI image: response had neither b64_json nor url")
        raise GenerationProviderRequestError(f"OpenAI returned no usable image data: {str(payload)[:300]}")

    async def _download(self, url: str) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=60.0, transport=self._transport) as client:
                response = await client.get(url)
        except httpx.RequestError as exc:
            logger.warning("OpenAI image: download failed: %s", exc)
            raise GenerationProviderUnavailableError(f"Could not download the generated image: {exc}") from exc
        if response.status_code != 200:
            logger.warning("OpenAI image: download returned status %s", response.status_code)
            error_cls = classify_http_error(response.status_code, response.text)
            raise error_cls(f"Downloading the generated image failed ({response.status_code}).")
        return response.content


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

    async def enhance(
        self, image: bytes, image_content_type: str, prompt: str, width: int = 1024, height: int = 1024
    ) -> GeneratedImage:
        raise GenerationProviderNotConfiguredError(not_configured_reason())
