import logging

import httpx

from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import (
    GenerationProviderNotConfiguredError,
    GenerationProviderRequestError,
    GenerationProviderUnavailableError,
    classify_http_error,
)
from app.integrations.generation.voice.base import ClonedVoiceProfile, VoiceProvider, VoiceSynthesisResult

logger = logging.getLogger("app.integrations.generation.voice")

_API_BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsVoiceProvider(VoiceProvider):
    """Real voice cloning + cloned-voice synthesis via the ElevenLabs API.
    Selected as the "cloud" VOICE_PROVIDER once ELEVENLABS_API_KEY is set
    — a separate credential from OPENAI_API_KEY, since OpenAI has no
    voice-cloning endpoint. `clone_voice` never proceeds without explicit
    consent (see base.py); any HTTP failure raises a classified
    GenerationProviderError — never a fabricated voice/audio."""

    def __init__(self, api_key: str, model: str, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._transport = transport

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(
            available=True, provider="elevenlabs", mode="production", reason=f"Configured with model {self._model}."
        )

    async def clone_voice(self, sample_audio: bytes, consent_confirmed: bool, name: str = "Cloned voice") -> ClonedVoiceProfile:
        if not consent_confirmed:
            raise ValueError("Voice cloning requires explicit confirmation that you have permission to use this voice.")

        headers = {"xi-api-key": self._api_key}
        data = {"name": name}
        files = {"files": ("sample.audio", sample_audio, "application/octet-stream")}

        logger.info("ElevenLabs: submitting voice clone request, name=%s bytes=%d", name, len(sample_audio))
        try:
            async with httpx.AsyncClient(timeout=120.0, transport=self._transport) as client:
                response = await client.post(f"{_API_BASE}/voices/add", headers=headers, data=data, files=files)
        except httpx.RequestError as exc:
            logger.warning("ElevenLabs: clone request failed: %s", exc)
            raise GenerationProviderUnavailableError(f"Could not reach the ElevenLabs API: {exc}") from exc

        if response.status_code != 200:
            logger.warning("ElevenLabs: clone request returned status %s", response.status_code)
            error_cls = classify_http_error(response.status_code, response.text)
            raise error_cls(f"ElevenLabs voice cloning failed ({response.status_code}): {response.text[:300]}")

        payload = response.json()
        voice_id = payload.get("voice_id")
        if not voice_id:
            raise GenerationProviderRequestError(f"ElevenLabs returned no voice_id: {str(payload)[:300]}")

        logger.info("ElevenLabs: voice cloned successfully, voice_id=%s", voice_id)
        return ClonedVoiceProfile(provider_ref=voice_id)

    async def synthesize_with_voice(self, text: str, profile: ClonedVoiceProfile) -> VoiceSynthesisResult:
        headers = {"xi-api-key": self._api_key}
        body = {"text": text, "model_id": self._model}

        logger.info("ElevenLabs: submitting synthesis request voice_id=%s", profile.provider_ref)
        try:
            async with httpx.AsyncClient(timeout=60.0, transport=self._transport) as client:
                response = await client.post(
                    f"{_API_BASE}/text-to-speech/{profile.provider_ref}", headers=headers, json=body
                )
        except httpx.RequestError as exc:
            logger.warning("ElevenLabs: synthesis request failed: %s", exc)
            raise GenerationProviderUnavailableError(f"Could not reach the ElevenLabs API: {exc}") from exc

        if response.status_code != 200:
            logger.warning("ElevenLabs: synthesis request returned status %s", response.status_code)
            error_cls = classify_http_error(response.status_code, response.text)
            raise error_cls(f"ElevenLabs speech synthesis failed ({response.status_code}): {response.text[:300]}")

        data = response.content
        if not data:
            raise GenerationProviderRequestError("ElevenLabs returned no audio data.")

        logger.info("ElevenLabs: synthesis succeeded, %d bytes", len(data))
        return VoiceSynthesisResult(data=data, format="mp3", content_type="audio/mpeg")

    async def delete_voice(self, profile: ClonedVoiceProfile) -> None:
        headers = {"xi-api-key": self._api_key}
        logger.info("ElevenLabs: deleting voice_id=%s", profile.provider_ref)
        try:
            async with httpx.AsyncClient(timeout=30.0, transport=self._transport) as client:
                response = await client.delete(f"{_API_BASE}/voices/{profile.provider_ref}", headers=headers)
        except httpx.RequestError as exc:
            logger.warning("ElevenLabs: delete request failed: %s", exc)
            raise GenerationProviderUnavailableError(f"Could not reach the ElevenLabs API: {exc}") from exc

        # A 404 here means the vendor has already lost track of this
        # voice (deleted out of band, expired, etc.) — not a failure from
        # the caller's point of view, since the end state (voice gone) is
        # exactly what was requested.
        if response.status_code not in (200, 404):
            logger.warning("ElevenLabs: delete request returned status %s", response.status_code)
            error_cls = classify_http_error(response.status_code, response.text)
            raise error_cls(f"ElevenLabs voice deletion failed ({response.status_code}): {response.text[:300]}")


def not_configured_reason() -> str:
    return (
        "ElevenLabs voice cloning is not configured. Set ELEVENLABS_API_KEY "
        "in the backend environment, then restart the server — this is a "
        "separate credential from OPENAI_API_KEY/GEMINI_API_KEY."
    )


class UnconfiguredElevenLabsVoiceProvider(VoiceProvider):
    """Selected when VOICE_PROVIDER=cloud but no ElevenLabs key is set."""

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(available=False, provider="elevenlabs", mode="production", reason=not_configured_reason())

    async def clone_voice(self, sample_audio: bytes, consent_confirmed: bool, name: str = "Cloned voice") -> ClonedVoiceProfile:
        if not consent_confirmed:
            raise ValueError("Voice cloning requires explicit confirmation that you have permission to use this voice.")
        raise GenerationProviderNotConfiguredError(not_configured_reason())

    async def synthesize_with_voice(self, text: str, profile: ClonedVoiceProfile) -> VoiceSynthesisResult:
        raise GenerationProviderNotConfiguredError(not_configured_reason())

    async def delete_voice(self, profile: ClonedVoiceProfile) -> None:
        raise GenerationProviderNotConfiguredError(not_configured_reason())
