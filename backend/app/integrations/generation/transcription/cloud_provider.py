import logging

import httpx

from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import (
    GenerationProviderNotConfiguredError,
    GenerationProviderRequestError,
    GenerationProviderUnavailableError,
    classify_http_error,
)
from app.integrations.generation.transcription.base import TranscriptionProvider, TranscriptionResult, TranscriptionSegment

logger = logging.getLogger("app.integrations.generation.transcription")

_API_URL = "https://api.openai.com/v1/audio/transcriptions"


class OpenAICloudTranscriptionProvider(TranscriptionProvider):
    """Real transcription via the OpenAI Audio API
    (`POST /v1/audio/transcriptions`, Whisper). Selected as the "cloud"
    TRANSCRIPTION_PROVIDER once OPENAI_API_KEY is set — the same
    credential already used for image/audio generation. Requests
    response_format=verbose_json so the real detected language and
    per-segment timing come back, not just a flat text string."""

    def __init__(self, api_key: str, model: str, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._transport = transport

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(
            available=True,
            provider="openai",
            mode="production",
            reason=f"Configured with model {self._model}.",
        )

    async def transcribe(self, audio_data: bytes, language: str | None = None) -> TranscriptionResult:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        data = {"model": self._model, "response_format": "verbose_json"}
        if language:
            data["language"] = language
        files = {"file": ("audio", audio_data, "application/octet-stream")}

        logger.info("OpenAI transcription: submitting request model=%s bytes=%d", self._model, len(audio_data))
        try:
            async with httpx.AsyncClient(timeout=180.0, transport=self._transport) as client:
                response = await client.post(_API_URL, headers=headers, data=data, files=files)
        except httpx.RequestError as exc:
            logger.warning("OpenAI transcription: request failed: %s", exc)
            raise GenerationProviderUnavailableError(f"Could not reach the OpenAI API: {exc}") from exc

        if response.status_code != 200:
            logger.warning("OpenAI transcription: request returned status %s", response.status_code)
            error_cls = classify_http_error(response.status_code, response.text)
            raise error_cls(f"OpenAI transcription failed ({response.status_code}): {response.text[:300]}")

        payload = response.json()
        text = payload.get("text")
        if text is None:
            raise GenerationProviderRequestError(f"OpenAI returned no transcription text: {str(payload)[:300]}")

        segments = [
            TranscriptionSegment(
                start_seconds=seg.get("start", 0.0),
                end_seconds=seg.get("end", 0.0),
                text=(seg.get("text") or "").strip(),
            )
            for seg in payload.get("segments") or []
        ]
        logger.info("OpenAI transcription: succeeded, %d chars, %d segments", len(text), len(segments))
        return TranscriptionResult(text=text.strip(), language=payload.get("language"), segments=segments)


def not_configured_reason() -> str:
    return (
        "OpenAI transcription is not configured. Set OPENAI_API_KEY in the "
        "backend environment, then restart the server — the same key used for "
        "image/audio generation also covers transcription."
    )


class UnconfiguredOpenAITranscriptionProvider(TranscriptionProvider):
    """Selected when TRANSCRIPTION_PROVIDER=cloud but no OpenAI key is set."""

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(available=False, provider="openai", mode="production", reason=not_configured_reason())

    async def transcribe(self, audio_data: bytes, language: str | None = None) -> TranscriptionResult:
        raise GenerationProviderNotConfiguredError(not_configured_reason())
