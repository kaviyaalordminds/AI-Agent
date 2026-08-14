import pytest

from app.core.config import get_settings
from app.integrations.claude.base import ClaudeMessage
from app.integrations.claude.errors import ProviderNotConfiguredError, ProviderRequestError
from app.integrations.claude.factory import get_claude_provider, get_claude_status
from app.integrations.claude.gemini_provider import GeminiProvider
from app.integrations.claude.ollama_provider import OllamaProvider


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture(autouse=True)
def _restore_ai_settings(settings):
    """These tests mutate the cached Settings singleton directly (same
    pattern as the storage/obsidian tmp-root fixtures) — restore every
    field afterwards so other test modules keep seeing the conftest
    baseline (AI_PROVIDER=anthropic)."""
    original = (
        settings.ai_provider,
        settings.ai_runtime_mode,
        settings.ollama_model,
        settings.ollama_base_url,
        settings.google_api_key,
    )
    yield
    (
        settings.ai_provider,
        settings.ai_runtime_mode,
        settings.ollama_model,
        settings.ollama_base_url,
        settings.google_api_key,
    ) = original


class TestRuntimeModeResolution:
    def test_local_mode_defaults_to_ollama(self, settings):
        settings.ai_runtime_mode = "local"
        settings.ai_provider = None
        assert settings.resolved_ai_runtime_mode == "local"
        assert settings.resolved_ai_provider == "ollama"

    def test_production_mode_defaults_to_anthropic(self, settings):
        settings.ai_runtime_mode = "production"
        settings.ai_provider = None
        assert settings.resolved_ai_provider == "anthropic"

    def test_explicit_provider_overrides_mode_default(self, settings):
        settings.ai_runtime_mode = "local"
        settings.ai_provider = "gemini"
        assert settings.resolved_ai_provider == "gemini"

    def test_app_env_drives_mode_when_unset(self, settings):
        settings.ai_runtime_mode = None
        original_env = settings.app_env
        try:
            settings.app_env = "production"
            assert settings.resolved_ai_runtime_mode == "production"
            settings.app_env = "development"
            assert settings.resolved_ai_runtime_mode == "local"
        finally:
            settings.app_env = original_env


class TestOllamaProvider:
    def test_not_configured_without_model(self, settings):
        settings.ai_provider = "ollama"
        settings.ollama_model = ""
        with pytest.raises(ProviderNotConfiguredError, match="OLLAMA_MODEL"):
            get_claude_provider()

    def test_status_reports_configured_once_model_set(self, settings):
        settings.ai_provider = "ollama"
        settings.ollama_model = "llama3.1"
        settings.ollama_base_url = "http://localhost:11434"
        provider = get_claude_provider()
        assert isinstance(provider, OllamaProvider)
        status = provider.status()
        assert status.configured is True
        assert status.provider == "ollama"
        assert status.model == "llama3.1"

    @pytest.mark.asyncio
    async def test_unreachable_ollama_raises_real_error_not_fake_response(self, settings):
        """No Ollama server is running in the test environment — this must
        surface as a real ProviderRequestError, never a fabricated reply."""
        settings.ai_provider = "ollama"
        settings.ollama_model = "llama3.1"
        settings.ollama_base_url = "http://localhost:11434"
        provider = get_claude_provider()

        with pytest.raises(ProviderRequestError, match="Could not reach Ollama"):
            async for _ in provider.stream([ClaudeMessage(role="user", content="hi")], "system"):
                pass

    def test_status_endpoint_reports_unconfigured_ollama_honestly(self, settings):
        settings.ai_provider = "ollama"
        settings.ollama_model = ""
        status = get_claude_status()
        assert status.configured is False
        assert status.provider == "ollama"
        assert "OLLAMA_MODEL" in status.detail


class TestGeminiProvider:
    def test_not_configured_without_api_key(self, settings):
        settings.ai_provider = "gemini"
        settings.google_api_key = None
        with pytest.raises(ProviderNotConfiguredError, match="GOOGLE_API_KEY"):
            get_claude_provider()

    def test_status_reports_configured_once_key_set(self, settings):
        settings.ai_provider = "gemini"
        settings.google_api_key = "fake-test-key-not-a-real-credential"
        provider = get_claude_provider()
        assert isinstance(provider, GeminiProvider)
        status = provider.status()
        assert status.configured is True
        assert status.provider == "gemini"


class TestUnknownProvider:
    def test_unknown_provider_name_raises_not_configured(self, settings, monkeypatch):
        settings.ai_provider = "anthropic"
        # resolved_ai_provider is a computed property backed by a Literal
        # field, so simulate an invalid value the way a stale/rolled-back
        # deploy might produce, without fighting pydantic's validation.
        monkeypatch.setattr(type(settings), "resolved_ai_provider", property(lambda self: "made-up-provider"))
        with pytest.raises(ProviderNotConfiguredError, match="Unknown AI_PROVIDER"):
            get_claude_provider()
