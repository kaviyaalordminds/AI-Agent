from app.core.config import get_settings
from app.integrations.claude.anthropic_provider import AnthropicApiProvider
from app.integrations.claude.base import ClaudeProvider, ProviderStatus
from app.integrations.claude.errors import ProviderNotConfiguredError
from app.integrations.claude.gemini_provider import GeminiProvider

_ANTHROPIC_NOT_CONFIGURED = (
    "Claude provider is not configured. Please configure the Anthropic API "
    "credentials in the backend environment (set ANTHROPIC_API_KEY, and "
    "optionally CLAUDE_MODEL, then restart the server)."
)
_GEMINI_NOT_CONFIGURED = (
    "Gemini provider is not configured. Set the GOOGLE_API_KEY environment "
    "variable (and optionally GEMINI_MODEL) on the backend, then restart "
    "the server."
)


def get_claude_provider() -> ClaudeProvider:
    """Construct this deployment's configured AI provider, or raise
    ProviderNotConfiguredError with actionable setup instructions.

    Despite the module name (kept for backward compatibility — every
    caller across agents/, knowledge/, and documents/ already imports
    from here), this is the general AI-provider factory: which concrete
    provider it builds is driven by AI_PROVIDER. Anthropic (Claude) is the
    default in every runtime mode; AI_PROVIDER=gemini switches to Gemini.
    There is no Ollama or other local/self-hosted LLM option — this
    application never uses a local LLM for chat/reasoning. See
    Settings.resolved_ai_provider in app/core/config.py.

    Deliberately not cached: configuration status must always reflect the
    current environment, not a stale value from before a key was added.
    """
    settings = get_settings()
    provider_name = settings.resolved_ai_provider

    if provider_name == "anthropic":
        if not settings.anthropic_api_key:
            raise ProviderNotConfiguredError(_ANTHROPIC_NOT_CONFIGURED)
        return AnthropicApiProvider(
            api_key=settings.anthropic_api_key,
            model=settings.claude_model,
            max_output_tokens=settings.claude_max_output_tokens,
        )

    if provider_name == "gemini":
        if not settings.google_api_key:
            raise ProviderNotConfiguredError(_GEMINI_NOT_CONFIGURED)
        return GeminiProvider(api_key=settings.google_api_key, model=settings.gemini_model)

    raise ProviderNotConfiguredError(f"Unknown AI_PROVIDER '{provider_name}'.")


def get_claude_status() -> ProviderStatus:
    """Never raises — always returns a real status object, configured or not."""
    try:
        return get_claude_provider().status()
    except ProviderNotConfiguredError as exc:
        settings = get_settings()
        return ProviderStatus(
            configured=False,
            provider=settings.resolved_ai_provider,
            model=None,
            detail=str(exc),
        )
