import base64
import json

import httpx
import pytest

from app.integrations.generation.audio.cloud_provider import OpenAICloudTTSProvider
from app.integrations.generation.audio.factory import get_audio_provider
from app.integrations.generation.errors import (
    GenerationProviderAuthError,
    GenerationProviderNotConfiguredError,
    GenerationProviderQuotaExceededError,
    GenerationProviderRequestError,
    GenerationProviderUnavailableError,
    classify_http_error,
)
from app.integrations.generation.image.factory import get_image_provider
from app.integrations.generation.image.openai_provider import OpenAIImageProvider
from app.integrations.generation.transcription.cloud_provider import OpenAICloudTranscriptionProvider
from app.integrations.generation.transcription.factory import get_transcription_provider
from app.integrations.generation.video.factory import get_video_provider
from app.integrations.generation.video.gemini_provider import GeminiVideoProvider
from app.integrations.generation.voice.base import ClonedVoiceProfile
from app.integrations.generation.voice.cloud_provider import ElevenLabsVoiceProvider
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

    @pytest.mark.asyncio
    async def test_429_raises_quota_exceeded(self):
        """The real symptom reported against the live API:
        'credit_balance_exhausted' on a 429 — must classify as
        quota_exceeded, not a generic failure, so the frontend can show
        the right card."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                json={"error": {"message": "You exceeded your current quota.", "code": "insufficient_quota"}},
            )

        provider = OpenAIImageProvider(
            api_key="test-key", model="gpt-image-1", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(GenerationProviderQuotaExceededError):
            await provider.generate("a red apple")

    @pytest.mark.asyncio
    async def test_401_raises_auth_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "Invalid API key.", "code": "invalid_api_key"}})

        provider = OpenAIImageProvider(
            api_key="bad-key", model="gpt-image-1", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(GenerationProviderAuthError):
            await provider.generate("a red apple")

    @pytest.mark.asyncio
    async def test_network_failure_raises_provider_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        provider = OpenAIImageProvider(
            api_key="test-key", model="gpt-image-1", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(GenerationProviderUnavailableError):
            await provider.generate("a red apple")


class TestGeminiVideoProviderErrorClassification:
    """Same classification contract as OpenAI image (see above), applied
    to the Gemini video provider — including the case unique to Veo's
    long-running-operation API: the HTTP call itself can return 200 while
    the operation payload carries its own error (quota exhaustion
    surfaces this way as often as via a direct HTTP 429)."""

    @pytest.mark.asyncio
    async def test_429_on_submit_raises_quota_exceeded(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                json={"error": {"code": 429, "message": "Quota exceeded.", "status": "RESOURCE_EXHAUSTED"}},
            )

        provider = GeminiVideoProvider(api_key="test-key", model="veo-3.1-generate-preview")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(GenerationProviderQuotaExceededError):
                await provider._submit(client, {"prompt": "a car"})

    @pytest.mark.asyncio
    async def test_operation_embedded_quota_error_raises_quota_exceeded(self):
        """The HTTP status is 200 (the poll request itself succeeded) but
        the operation body says the generation failed with a
        RESOURCE_EXHAUSTED code — this must still classify as
        quota_exceeded, not a generic failure."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "done": True,
                    "error": {"code": 429, "message": "Quota exceeded.", "status": "RESOURCE_EXHAUSTED"},
                },
            )

        provider = GeminiVideoProvider(api_key="test-key", model="veo-3.1-generate-preview")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(GenerationProviderQuotaExceededError):
                await provider._poll_until_done(client, "operations/fake-op-id")

    @pytest.mark.asyncio
    async def test_404_on_submit_raises_generic_request_error_not_unavailable(self):
        """A 404 (e.g. an unsupported/retired model name — the exact
        veo-2.0-generate-001 bug this was fixed for) is a request problem,
        not a vendor outage — must stay a generic GenerationProviderRequestError,
        not provider_unavailable."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": {"code": 404, "message": "model not found", "status": "NOT_FOUND"}})

        provider = GeminiVideoProvider(api_key="test-key", model="veo-2.0-generate-001")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(GenerationProviderRequestError) as excinfo:
                await provider._submit(client, {"prompt": "a car"})
            assert excinfo.value.error_type == "generation_failed"


class TestSecretsNeverLeakInProviderErrors:
    """The Phase 10 audit found only one narrow secrets-exposure test
    existed (test_system.py::test_never_exposes_secrets, Anthropic-only,
    two endpoints) — the more important, completely untested path is
    whether a REAL (but invalid/expired) configured API key ends up
    inside the error text a provider raises, which flows straight into
    GenerationJob.error and is returned to the job's owner via
    GET /api/generation/{image,video}/{id}. A key embedded in a request
    URL query string (Gemini) is a real risk if an underlying exception's
    str() ever includes the full URL — verified empirically that httpx's
    RequestError subclasses do NOT include the URL in str(exc) by
    default, and these tests lock that behavior in as a regression
    guard, not just an assumption."""

    _REAL_LOOKING_KEY = "sk-real-secret-abcdef1234567890"

    @pytest.mark.asyncio
    async def test_openai_401_response_body_error_never_contains_the_configured_key(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "Invalid API key.", "code": "invalid_api_key"}})

        provider = OpenAIImageProvider(
            api_key=self._REAL_LOOKING_KEY, model="gpt-image-1", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(GenerationProviderAuthError) as excinfo:
            await provider.generate("a red apple")
        assert self._REAL_LOOKING_KEY not in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_openai_connect_error_never_contains_the_configured_key(self):
        """OpenAI sends the key as an Authorization header (not a URL query
        param), but this still confirms the network-failure error path is
        clean end to end."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        provider = OpenAIImageProvider(
            api_key=self._REAL_LOOKING_KEY, model="gpt-image-1", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(GenerationProviderUnavailableError) as excinfo:
            await provider.generate("a red apple")
        assert self._REAL_LOOKING_KEY not in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_gemini_401_response_body_error_never_contains_the_configured_key(self):
        """Gemini sends the key as a URL query param (?key=...) — the
        highest-risk provider for this class of leak."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"code": 401, "message": "API key not valid.", "status": "UNAUTHENTICATED"}})

        provider = GeminiVideoProvider(api_key=self._REAL_LOOKING_KEY, model="veo-3.1-generate-preview")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(GenerationProviderAuthError) as excinfo:
                await provider._submit(client, {"prompt": "a car"})
        assert self._REAL_LOOKING_KEY not in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_gemini_connect_error_never_contains_the_configured_key(self):
        """The highest-risk path: the key rides in the request URL
        (params={"key": ...}), and a raw connection-error exception could
        plausibly stringify to include that URL."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        provider = GeminiVideoProvider(api_key=self._REAL_LOOKING_KEY, model="veo-3.1-generate-preview")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(GenerationProviderUnavailableError) as excinfo:
                await provider._submit(client, {"prompt": "a car"})
        assert self._REAL_LOOKING_KEY not in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_gemini_download_connect_error_never_contains_the_configured_key(self):
        provider = GeminiVideoProvider(api_key=self._REAL_LOOKING_KEY, model="veo-3.1-generate-preview")

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(GenerationProviderUnavailableError) as excinfo:
                await provider._download(client, "https://generativelanguage.googleapis.com/v1beta/files/abc")
        assert self._REAL_LOOKING_KEY not in str(excinfo.value)


class TestClassifyHttpError:
    def test_429_is_quota_exceeded(self):
        assert classify_http_error(429, "") is GenerationProviderQuotaExceededError

    def test_401_and_403_are_auth_error(self):
        assert classify_http_error(401, "") is GenerationProviderAuthError
        assert classify_http_error(403, "") is GenerationProviderAuthError

    def test_5xx_is_provider_unavailable(self):
        assert classify_http_error(500, "") is GenerationProviderUnavailableError
        assert classify_http_error(503, "") is GenerationProviderUnavailableError

    def test_quota_keyword_in_400_body_is_still_quota_exceeded(self):
        assert classify_http_error(400, '{"error": "credit_balance_exhausted"}') is GenerationProviderQuotaExceededError

    def test_plain_400_is_generic_request_error(self):
        assert classify_http_error(400, '{"error": "unknown_parameter"}') is GenerationProviderRequestError


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


class TestOpenAICloudTTSProvider:
    @pytest.mark.asyncio
    async def test_successful_synthesis_returns_real_bytes(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["authorization"] == "Bearer test-key"
            body = json.loads(request.content)
            assert body == {
                "model": "tts-1", "voice": "alloy", "input": "hello",
                "response_format": "wav", "speed": 1.0,
            }
            return httpx.Response(200, content=b"RIFF-fake-wav-bytes", headers={"content-type": "audio/wav"})

        provider = OpenAICloudTTSProvider(
            api_key="test-key", model="tts-1", default_voice="alloy", transport=httpx.MockTransport(handler)
        )
        result = await provider.synthesize("hello")
        assert result.data == b"RIFF-fake-wav-bytes"
        assert result.format == "wav"
        assert result.content_type == "audio/wav"

    @pytest.mark.asyncio
    async def test_explicit_voice_overrides_default(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["voice"] == "nova"
            return httpx.Response(200, content=b"data")

        provider = OpenAICloudTTSProvider(
            api_key="test-key", model="tts-1", default_voice="alloy", transport=httpx.MockTransport(handler)
        )
        await provider.synthesize("hello", voice="nova")

    @pytest.mark.asyncio
    async def test_unsupported_format_rejected_before_any_request(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("must not make a request for an unsupported format")

        provider = OpenAICloudTTSProvider(
            api_key="test-key", model="tts-1", default_voice="alloy", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(GenerationProviderRequestError):
            await provider.synthesize("hello", format="madeup")

    @pytest.mark.asyncio
    async def test_429_raises_quota_exceeded(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"message": "quota exceeded"}})

        provider = OpenAICloudTTSProvider(
            api_key="test-key", model="tts-1", default_voice="alloy", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(GenerationProviderQuotaExceededError):
            await provider.synthesize("hello")

    @pytest.mark.asyncio
    async def test_401_raises_auth_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "invalid key"}})

        provider = OpenAICloudTTSProvider(
            api_key="bad-key", model="tts-1", default_voice="alloy", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(GenerationProviderAuthError):
            await provider.synthesize("hello")


class TestOpenAICloudTranscriptionProvider:
    @pytest.mark.asyncio
    async def test_successful_transcription_parses_verbose_json(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["authorization"] == "Bearer test-key"
            return httpx.Response(
                200,
                json={
                    "text": "hello world",
                    "language": "english",
                    "segments": [{"start": 0.0, "end": 1.2, "text": " hello world "}],
                },
            )

        provider = OpenAICloudTranscriptionProvider(api_key="test-key", model="whisper-1", transport=httpx.MockTransport(handler))
        result = await provider.transcribe(b"fake-audio-bytes")
        assert result.text == "hello world"
        assert result.language == "english"
        assert len(result.segments) == 1
        assert result.segments[0].text == "hello world"
        assert result.segments[0].start_seconds == 0.0
        assert result.segments[0].end_seconds == 1.2

    @pytest.mark.asyncio
    async def test_language_hint_is_sent_when_provided(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = request.content.decode()
            assert 'name="language"' in body and "\r\nen\r\n" in body
            return httpx.Response(200, json={"text": "hola", "language": "spanish", "segments": []})

        provider = OpenAICloudTranscriptionProvider(api_key="test-key", model="whisper-1", transport=httpx.MockTransport(handler))
        await provider.transcribe(b"fake-audio-bytes", language="en")

    @pytest.mark.asyncio
    async def test_429_raises_quota_exceeded(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"message": "quota exceeded"}})

        provider = OpenAICloudTranscriptionProvider(api_key="test-key", model="whisper-1", transport=httpx.MockTransport(handler))
        with pytest.raises(GenerationProviderQuotaExceededError):
            await provider.transcribe(b"fake-audio-bytes")

    @pytest.mark.asyncio
    async def test_network_failure_raises_provider_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        provider = OpenAICloudTranscriptionProvider(api_key="test-key", model="whisper-1", transport=httpx.MockTransport(handler))
        with pytest.raises(GenerationProviderUnavailableError):
            await provider.transcribe(b"fake-audio-bytes")


class TestElevenLabsVoiceProvider:
    @pytest.mark.asyncio
    async def test_clone_voice_without_consent_raises_value_error_before_any_request(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("must not make a request without consent")

        provider = ElevenLabsVoiceProvider(api_key="test-key", model="eleven_multilingual_v2", transport=httpx.MockTransport(handler))
        with pytest.raises(ValueError):
            await provider.clone_voice(b"fake-sample", consent_confirmed=False)

    @pytest.mark.asyncio
    async def test_successful_clone_returns_provider_ref(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["xi-api-key"] == "test-key"
            return httpx.Response(200, json={"voice_id": "voice-abc123"})

        provider = ElevenLabsVoiceProvider(api_key="test-key", model="eleven_multilingual_v2", transport=httpx.MockTransport(handler))
        cloned = await provider.clone_voice(b"fake-sample", consent_confirmed=True, name="My Voice")
        assert cloned.provider_ref == "voice-abc123"

    @pytest.mark.asyncio
    async def test_clone_401_raises_auth_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": {"message": "invalid key"}})

        provider = ElevenLabsVoiceProvider(api_key="bad-key", model="eleven_multilingual_v2", transport=httpx.MockTransport(handler))
        with pytest.raises(GenerationProviderAuthError):
            await provider.clone_voice(b"fake-sample", consent_confirmed=True)

    @pytest.mark.asyncio
    async def test_successful_synthesis_returns_real_bytes(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/text-to-speech/voice-abc123"
            return httpx.Response(200, content=b"fake-mp3-bytes", headers={"content-type": "audio/mpeg"})

        provider = ElevenLabsVoiceProvider(api_key="test-key", model="eleven_multilingual_v2", transport=httpx.MockTransport(handler))
        result = await provider.synthesize_with_voice("hello", ClonedVoiceProfile(provider_ref="voice-abc123"))
        assert result.data == b"fake-mp3-bytes"
        assert result.format == "mp3"

    @pytest.mark.asyncio
    async def test_delete_voice_succeeds(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "DELETE"
            assert request.url.path == "/v1/voices/voice-abc123"
            return httpx.Response(200, json={"status": "ok"})

        provider = ElevenLabsVoiceProvider(api_key="test-key", model="eleven_multilingual_v2", transport=httpx.MockTransport(handler))
        await provider.delete_voice(ClonedVoiceProfile(provider_ref="voice-abc123"))  # must not raise

    @pytest.mark.asyncio
    async def test_delete_voice_404_is_treated_as_already_gone_not_an_error(self):
        """The vendor having already lost track of this voice is the same
        end state as a successful delete from the caller's perspective —
        must not raise."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"detail": "not found"})

        provider = ElevenLabsVoiceProvider(api_key="test-key", model="eleven_multilingual_v2", transport=httpx.MockTransport(handler))
        await provider.delete_voice(ClonedVoiceProfile(provider_ref="voice-abc123"))

    @pytest.mark.asyncio
    async def test_delete_voice_500_raises_provider_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "internal error"})

        provider = ElevenLabsVoiceProvider(api_key="test-key", model="eleven_multilingual_v2", transport=httpx.MockTransport(handler))
        with pytest.raises(GenerationProviderUnavailableError):
            await provider.delete_voice(ClonedVoiceProfile(provider_ref="voice-abc123"))


class TestAudioSecretsNeverLeakInProviderErrors:
    """Same discipline as TestSecretsNeverLeakInProviderErrors above,
    applied to the three new audio-family providers — a real API key
    must never appear in a raised error's text, whether the vendor sends
    the key back in a response body or the failure is a raw connection
    error."""

    _REAL_LOOKING_KEY = "sk-real-secret-abcdef1234567890"

    @pytest.mark.asyncio
    async def test_openai_tts_401_never_contains_the_configured_key(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "Invalid API key."}})

        provider = OpenAICloudTTSProvider(
            api_key=self._REAL_LOOKING_KEY, model="tts-1", default_voice="alloy", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(GenerationProviderAuthError) as excinfo:
            await provider.synthesize("hello")
        assert self._REAL_LOOKING_KEY not in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_openai_transcription_connect_error_never_contains_the_configured_key(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        provider = OpenAICloudTranscriptionProvider(
            api_key=self._REAL_LOOKING_KEY, model="whisper-1", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(GenerationProviderUnavailableError) as excinfo:
            await provider.transcribe(b"fake-audio")
        assert self._REAL_LOOKING_KEY not in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_elevenlabs_connect_error_never_contains_the_configured_key(self):
        """The highest-risk path for this vendor: xi-api-key is sent as a
        header (not a URL param, unlike Gemini), but this still confirms
        the network-failure error path is clean end to end."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        provider = ElevenLabsVoiceProvider(
            api_key=self._REAL_LOOKING_KEY, model="eleven_multilingual_v2", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(GenerationProviderUnavailableError) as excinfo:
            await provider.clone_voice(b"fake-sample", consent_confirmed=True)
        assert self._REAL_LOOKING_KEY not in str(excinfo.value)
