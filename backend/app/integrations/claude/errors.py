class ClaudeProviderError(Exception):
    """Base class for Claude provider failures."""


class ProviderNotConfiguredError(ClaudeProviderError):
    """Raised when no real Claude credentials are configured.

    Callers must surface this to the user as an actionable configuration
    error — never fall back to a fake or mocked response."""


class ProviderRequestError(ClaudeProviderError):
    """Raised when a configured provider's API call itself fails
    (network error, auth rejected, rate limited, etc.)."""
