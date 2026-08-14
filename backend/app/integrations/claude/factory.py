from app.core.config import get_settings
from app.integrations.claude.anthropic_provider import AnthropicApiProvider
from app.integrations.claude.base import ClaudeProvider, ProviderStatus
from app.integrations.claude.errors import ProviderNotConfiguredError

_SETUP_INSTRUCTIONS = (
    "Set the ANTHROPIC_API_KEY environment variable (and optionally "
    "CLAUDE_MODEL) on the backend, then restart the server."
)


def get_claude_provider() -> ClaudeProvider:
    """Construct the configured Claude provider, or raise
    ProviderNotConfiguredError with actionable setup instructions.

    Deliberately not cached: configuration status must always reflect the
    current environment, not a stale value from before a key was added.
    """
    settings = get_settings()

    if settings.claude_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ProviderNotConfiguredError(
                f"No Claude provider is configured. {_SETUP_INSTRUCTIONS}"
            )
        return AnthropicApiProvider(
            api_key=settings.anthropic_api_key,
            model=settings.claude_model,
            max_output_tokens=settings.claude_max_output_tokens,
        )

    raise ProviderNotConfiguredError(f"Unknown CLAUDE_PROVIDER '{settings.claude_provider}'.")


def get_claude_status() -> ProviderStatus:
    """Never raises — always returns a real status object, configured or not."""
    try:
        return get_claude_provider().status()
    except ProviderNotConfiguredError as exc:
        settings = get_settings()
        return ProviderStatus(
            configured=False,
            provider=settings.claude_provider,
            model=None,
            detail=str(exc),
        )
