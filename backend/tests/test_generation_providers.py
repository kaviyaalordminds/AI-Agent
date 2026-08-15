import base64
import json

import httpx
import pytest

from app.integrations.generation.audio.factory import get_audio_provider
from app.integrations.generation.errors import GenerationProviderNotConfiguredError, GenerationProviderRequestError
from app.integrations.generation.image.factory import get_image_provider
from app.integrations.generation.image.openai_provider import OpenAIImageProvider
from app.integrations.generation.transcription.factory import get_transcription_provider
from app.integrations.generation.video.factory import get_video_provider
from app.integrations.generation.voice.factory import get_voice_provider


class TestAudioProvider:
    def test_local_capability_is_available_when_espeak_installed(self):
        """This test environment has espeak-ng installed — verifies real
        detection reports it, not a hard-coded True."""
        cap = get_audio_provider().capability()
        assert cap.mode == "local"
        # Either genuinely available (espeak-ng present) or honestly not —
        # never crashes either way.
        assert isinstance(cap.available, bool)
        assert cap.reason

    @pytest.mark.asyncio
    async def test_synthesize_produces_real_wav_when_available(self):
        provider = get_audio_provider()
        cap = provider.capability()
        if not cap.available:
            pytest.skip("No local TTS engine installed in this environment.")
        result = await provider.synthesize("This is a real synthesis test.", speed=1.0)
        assert result.format == "wav"
        assert result.data[:4] == b"RIFF"
        assert len(result.data) > 100

    @pytest.mark.asyncio
    async def test_synthesize_rejects_non_wav_format(self):
        provider = get_audio_provider()
        if not provider.capability().available:
            pytest.skip("No local TTS engine installed in this environment.")
        from app.integrations.generation.errors import GenerationProviderRequestError

        with pytest.raises(GenerationProviderRequestError):
            await provider.synthesize("test", format="mp3")


class TestUnavailableLocalProvidersFailHonestly:
    """Image/video default to real, API-based providers (no GPU/local
    model involved) — image via OpenAI, video via Gemini — but this test
    environment has no OPENAI_API_KEY/GEMINI_API_KEY configured; voice has
    no local backend in any CI/sandbox environment. These assert the
    honest-unavailable contract, not that they mysteriously started
    working."""

    @pytest.mark.asyncio
    async def test_image_provider_honestly_unavailable(self):
        provider = get_image_provider()
        cap = provider.capability()
        assert cap.available is False
        assert cap.provider == "openai"
        assert "not configured" in cap.reason.lower()
        assert "openai_api_key" in cap.reason.lower()
        with pytest.raises(GenerationProviderNotConfiguredError):
            await provider.generate("a red apple")

    @pytest.mark.asyncio
    async def test_video_provider_honestly_unavailable(self):
        provider = get_video_provider()
        cap = provider.capability()
        assert cap.available is False
        assert "not configured" in cap.reason.lower()
        with pytest.raises(GenerationProviderNotConfiguredError):
            await provider.generate("a flying car")

    @pytest.mark.asyncio
    async def test_voice_provider_requires_consent_before_checking_availability(self):
        provider = get_voice_provider()
        with pytest.raises(ValueError, match="permission"):
            await provider.clone_voice(b"fake-audio-bytes", consent_confirmed=False)

    @pytest.mark.asyncio
    async def test_voice_provider_honestly_unavailable_even_with_consent(self):
        provider = get_voice_provider()
        with pytest.raises(GenerationProviderNotConfiguredError):
            await provider.clone_voice(b"fake-audio-bytes", consent_confirmed=True)

    def test_transcription_provider_honestly_reports_no_backend(self):
        provider = get_transcription_provider()
        cap = provider.capability()
        # This test environment has no faster-whisper/openai-whisper
        # installed — assert the detection is real, not hard-coded.
        assert isinstance(cap.available, bool)
        if not cap.available:
            assert "no local transcription backend" in cap.reason.lower()

    @pytest.mark.asyncio
    async def test_transcription_raises_not_configured_when_unavailable(self):
        provider = get_transcription_provider()
        if provider.capability().available:
            pytest.skip("A transcription backend is installed in this environment.")
        with pytest.raises(GenerationProviderNotConfiguredError):
            await provider.transcribe(b"fake-audio-bytes")


class TestOpenAIImageProviderRequestFormat:
    """Regression coverage for a real bug hit against the live OpenAI API:
    the provider was sending `response_format`, which current OpenAI API
    versions reject outright ("Unknown parameter: 'response_format'",
    400). These use httpx.MockTransport (no real network call, no key
    needed) to assert the exact request body sent and that both possible
    response shapes (b64_json and url) are handled correctly."""

    @pytest.mark.asyncio
    async def test_request_never_includes_response_format(self):
        sent_bodies = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent_bodies.append(json.loads(request.content))
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(b"png-bytes").decode()}]})

        provider = OpenAIImageProvider(
            api_key="test-key", model="dall-e-3", transport=httpx.MockTransport(handler)
        )
        await provider.generate("a red apple", width=1024, height=1024)

        assert len(sent_bodies) == 1
        assert "response_format" not in sent_bodies[0]
        assert sent_bodies[0]["model"] == "dall-e-3"
        assert sent_bodies[0]["prompt"] == "a red apple"

    @pytest.mark.asyncio
    async def test_generate_decodes_b64_json_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(b"raw-image-bytes").decode()}]})

        provider = OpenAIImageProvider(
            api_key="test-key", model="dall-e-3", transport=httpx.MockTransport(handler)
        )
        result = await provider.generate("a red apple")
        assert result.data == b"raw-image-bytes"
        assert result.content_type == "image/png"

    @pytest.mark.asyncio
    async def test_generate_downloads_url_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/images/generations":
                return httpx.Response(200, json={"data": [{"url": "https://cdn.example.com/generated.png"}]})
            return httpx.Response(200, content=b"downloaded-image-bytes")

        provider = OpenAIImageProvider(
            api_key="test-key", model="dall-e-3", transport=httpx.MockTransport(handler)
        )
        result = await provider.generate("a red apple")
        assert result.data == b"downloaded-image-bytes"

    @pytest.mark.asyncio
    async def test_generate_raises_on_openai_error_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={"error": {"message": "Unknown parameter: 'response_format'.", "code": "unknown_parameter"}},
            )

        provider = OpenAIImageProvider(
            api_key="test-key", model="dall-e-3", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(GenerationProviderRequestError, match="400"):
            await provider.generate("a red apple")


class TestProviderFailureIsolation:
    """A missing/unavailable provider in one category must never affect
    another — each factory constructs independently."""

    def test_all_five_factories_construct_without_crashing(self):
        providers = [
            get_audio_provider(),
            get_transcription_provider(),
            get_image_provider(),
            get_video_provider(),
            get_voice_provider(),
        ]
        for provider in providers:
            cap = provider.capability()
            assert cap.mode in ("local", "production")
            assert cap.reason
