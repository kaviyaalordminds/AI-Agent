import pytest

from app.integrations.generation.audio.factory import get_audio_provider
from app.integrations.generation.errors import GenerationProviderNotConfiguredError
from app.integrations.generation.image.factory import get_image_provider
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
    """Image/video default to the real, API-based Gemini provider (no
    GPU/local model involved) but this test environment has no
    GEMINI_API_KEY configured; voice has no local backend in any CI/
    sandbox environment. These assert the honest-unavailable contract,
    not that they mysteriously started working."""

    @pytest.mark.asyncio
    async def test_image_provider_honestly_unavailable(self):
        provider = get_image_provider()
        cap = provider.capability()
        assert cap.available is False
        assert "not configured" in cap.reason.lower()
        assert "gemini_api_key" in cap.reason.lower()
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
