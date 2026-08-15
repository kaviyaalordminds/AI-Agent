import asyncio
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
from app.integrations.generation.video.base import GeneratedVideo, VideoProvider

logger = logging.getLogger("app.integrations.generation.video")

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_POLL_INTERVAL_SECONDS = 8


class GeminiVideoProvider(VideoProvider):
    """Real video generation via the Gemini API's Veo models. Veo
    generation is a long-running operation — submit via
    `{model}:predictLongRunning`, then poll the returned operation name
    until done, then download the resulting video file. This is why
    video generation always runs through the GenerationJob queue (see
    app/jobs/worker.py) rather than inside an HTTP request: a single
    generation can take minutes.

    Selected as the "cloud" VIDEO_PROVIDER once GEMINI_API_KEY (or
    GOOGLE_API_KEY) is set. Any HTTP failure, timeout, or malformed
    response raises GenerationProviderRequestError — never a fabricated
    video."""

    def __init__(self, api_key: str, model: str, max_wait_seconds: int = 590) -> None:
        self._api_key = api_key
        self._model = model
        self._max_wait_seconds = max_wait_seconds

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(
            available=True,
            provider="gemini",
            mode="production",
            reason=f"Configured with model {self._model}.",
        )

    async def generate(
        self, prompt: str, duration_seconds: float = 4.0, reference_image: bytes | None = None
    ) -> GeneratedVideo:
        instance: dict = {"prompt": prompt}
        if reference_image is not None:
            instance["image"] = {
                "bytesBase64Encoded": base64.b64encode(reference_image).decode("ascii"),
                "mimeType": "image/png",
            }

        async with httpx.AsyncClient(timeout=60.0) as client:
            operation_name = await self._submit(client, instance)
            video_uri = await self._poll_until_done(client, operation_name)
            data = await self._download(client, video_uri)

        return GeneratedVideo(data=data, format="mp4", content_type="video/mp4", duration_seconds=duration_seconds)

    async def _submit(self, client: httpx.AsyncClient, instance: dict) -> str:
        url = f"{_API_BASE}/models/{self._model}:predictLongRunning"
        logger.info("Gemini video: submitting request to model=%s", self._model)
        try:
            response = await client.post(url, params={"key": self._api_key}, json={"instances": [instance]})
        except httpx.RequestError as exc:
            logger.warning("Gemini video: request to submit generation failed: %s", exc)
            raise GenerationProviderUnavailableError(f"Could not reach the Gemini API: {exc}") from exc

        if response.status_code != 200:
            logger.warning("Gemini video: submit failed with status %s", response.status_code)
            error_cls = classify_http_error(response.status_code, response.text)
            raise error_cls(
                f"Gemini video generation request failed ({response.status_code}): {response.text[:300]}"
            )
        name = response.json().get("name")
        if not name:
            raise GenerationProviderRequestError("Gemini did not return an operation name for this video job.")
        logger.info("Gemini video: operation submitted, polling for completion")
        return name

    async def _poll_until_done(self, client: httpx.AsyncClient, operation_name: str) -> str:
        elapsed = 0
        while elapsed < self._max_wait_seconds:
            try:
                response = await client.get(f"{_API_BASE}/{operation_name}", params={"key": self._api_key})
            except httpx.RequestError as exc:
                logger.warning("Gemini video: status check failed at %ss elapsed: %s", elapsed, exc)
                raise GenerationProviderUnavailableError(f"Could not reach the Gemini API: {exc}") from exc

            if response.status_code != 200:
                logger.warning(
                    "Gemini video: status check returned %s at %ss elapsed", response.status_code, elapsed
                )
                error_cls = classify_http_error(response.status_code, response.text)
                raise error_cls(
                    f"Gemini video status check failed ({response.status_code}): {response.text[:300]}"
                )
            payload = response.json()
            if payload.get("done"):
                if "error" in payload:
                    # The HTTP call itself succeeded (200) but the async
                    # operation completed with a failure — e.g. quota
                    # exhaustion surfaces here, not as an HTTP error status,
                    # so it needs the same classification treatment.
                    op_error = payload["error"]
                    logger.warning("Gemini video: generation finished with an error: %s", op_error)
                    error_cls = classify_http_error(op_error.get("code", 500), str(op_error))
                    raise error_cls(f"Gemini video generation failed: {op_error}")
                logger.info("Gemini video: generation completed after %ss", elapsed)
                return self._extract_video_uri(payload)

            logger.debug("Gemini video: still processing at %ss elapsed", elapsed)
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

        logger.warning("Gemini video: generation did not finish within %ss", self._max_wait_seconds)
        raise GenerationProviderRequestError(
            f"Gemini video generation did not finish within {self._max_wait_seconds} seconds."
        )

    @staticmethod
    def _extract_video_uri(payload: dict) -> str:
        try:
            samples = payload["response"]["generateVideoResponse"]["generatedSamples"]
            return samples[0]["video"]["uri"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GenerationProviderRequestError(
                f"Gemini finished but returned no usable video: {str(payload)[:300]}"
            ) from exc

    async def _download(self, client: httpx.AsyncClient, video_uri: str) -> bytes:
        try:
            response = await client.get(video_uri, params={"key": self._api_key})
        except httpx.RequestError as exc:
            logger.warning("Gemini video: download failed: %s", exc)
            raise GenerationProviderUnavailableError(f"Could not download the generated video: {exc}") from exc
        if response.status_code != 200:
            logger.warning("Gemini video: download returned status %s", response.status_code)
            error_cls = classify_http_error(response.status_code, response.text)
            raise error_cls(f"Downloading the generated video failed ({response.status_code}).")
        logger.info("Gemini video: downloaded %d bytes", len(response.content))
        return response.content


def not_configured_reason() -> str:
    return (
        "Gemini video generation is not configured. Set GEMINI_API_KEY (or GOOGLE_API_KEY) "
        "and optionally GEMINI_VIDEO_MODEL in the backend environment, then restart the server."
    )


class UnconfiguredGeminiVideoProvider(VideoProvider):
    """Selected when VIDEO_PROVIDER=cloud but no Gemini key is set."""

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(available=False, provider="gemini", mode="production", reason=not_configured_reason())

    async def generate(
        self, prompt: str, duration_seconds: float = 4.0, reference_image: bytes | None = None
    ) -> GeneratedVideo:
        raise GenerationProviderNotConfiguredError(not_configured_reason())
