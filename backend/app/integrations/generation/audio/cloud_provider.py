import logging

import httpx

from app.integrations.capability import CapabilityStatus
from app.integrations.generation.audio.base import AudioProvider, SynthesizedAudio
from app.integrations.generation.errors import (
    GenerationProviderNotConfiguredError,
    GenerationProviderRequestError,
    GenerationProviderUnavailableError,
    classify_http_error,
)

logger = logging.getLogger("app.integrations.generation.audio")

_API_URL = "https://api.openai.com/v1/audio/speech"

# OpenAI's supported response_format values and the content-type each maps
# to — used both to validate the caller's requested `format` and to set
# the right Content-Type on the stored/served file.
_FORMAT_CONTENT_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/pcm",
}


class OpenAICloudTTSProvider(AudioProvider):
    """Real text-to-speech via the OpenAI Audio API
    (`POST /v1/audio/speech`). Selected as the "cloud" TTS_PROVIDER once
    OPENAI_API_KEY is set — the same credential already used for image
    generation. Any HTTP failure or malformed response raises
    GenerationProviderRequestError — never fabricated audio."""

    def __init__(self, api_key: str, model: str, default_voice: str, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._default_voice = default_voice
        # Injectable only for tests (httpx.MockTransport) — production
        # code never sets this.
        self._transport = transport

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(
            available=True,
            provider="openai",
            mode="production",
            reason=f"Configured with model {self._model}.",
        )

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language: str | None = None,
        speed: float = 1.0,
        format: str = "wav",
    ) -> SynthesizedAudio:
        if format not in _FORMAT_CONTENT_TYPES:
            raise GenerationProviderRequestError(
                f"Unsupported audio format '{format}' for OpenAI TTS. "
                f"Supported: {', '.join(sorted(_FORMAT_CONTENT_TYPES))}."
            )

        body = {
            "model": self._model,
            "voice": voice or self._default_voice,
            "input": text,
            "response_format": format,
            # OpenAI's supported range is 0.25-4.0; the request schema
            # (app/schemas/job.py) already constrains 0.5-2.0, well inside it.
            "speed": speed,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        logger.info("OpenAI TTS: submitting request model=%s voice=%s format=%s", self._model, body["voice"], format)
        try:
            async with httpx.AsyncClient(timeout=60.0, transport=self._transport) as client:
                response = await client.post(_API_URL, json=body, headers=headers)
        except httpx.RequestError as exc:
            logger.warning("OpenAI TTS: request failed: %s", exc)
            raise GenerationProviderUnavailableError(f"Could not reach the OpenAI API: {exc}") from exc

        if response.status_code != 200:
            logger.warning("OpenAI TTS: request returned status %s", response.status_code)
            error_cls = classify_http_error(response.status_code, response.text)
            raise error_cls(f"OpenAI audio generation failed ({response.status_code}): {response.text[:300]}")

        data = response.content
        if not data:
            raise GenerationProviderRequestError("OpenAI returned no audio data.")

        logger.info("OpenAI TTS: generation succeeded, %d bytes (%s)", len(data), format)
        return SynthesizedAudio(data=data, format=format, content_type=_FORMAT_CONTENT_TYPES[format])


def not_configured_reason() -> str:
    return (
        "OpenAI text-to-speech is not configured. Set OPENAI_API_KEY in the "
        "backend environment, then restart the server — the same key used for "
        "image generation also covers audio."
    )


class UnconfiguredOpenAITTSProvider(AudioProvider):
    """Selected when TTS_PROVIDER=cloud but no OpenAI key is set —
    honestly reports unavailable rather than only failing on synthesize()."""

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(available=False, provider="openai", mode="production", reason=not_configured_reason())

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language: str | None = None,
        speed: float = 1.0,
        format: str = "wav",
    ) -> SynthesizedAudio:
        raise GenerationProviderNotConfiguredError(not_configured_reason())
