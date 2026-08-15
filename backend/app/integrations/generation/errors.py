class GenerationProviderError(Exception):
    """Base class for audio/transcription/image/video/voice provider
    failures. `error_type` is a short, stable machine-readable code —
    persisted on GenerationJob.error_type (see app/jobs/worker.py) and
    read by the frontend to render the right error card/retry affordance
    instead of a generic message for every failure."""

    error_type: str = "generation_failed"


class GenerationProviderNotConfiguredError(GenerationProviderError):
    """Raised when a generation capability isn't installed/configured on
    this machine. Callers surface this as a structured, honest status —
    never fall back to a fake or mocked result."""

    error_type = "not_configured"


class GenerationProviderRequestError(GenerationProviderError):
    """Raised when an otherwise-available provider's actual call fails,
    for a reason not covered by a more specific subclass below."""

    error_type = "generation_failed"


class GenerationProviderQuotaExceededError(GenerationProviderRequestError):
    """The vendor rejected the request because of exhausted quota/credits
    or a rate limit (HTTP 429, or an account/billing-shaped error body).
    A real, valid credential is configured — this is not a config
    problem, it's exhausted usage."""

    error_type = "quota_exceeded"


class GenerationProviderAuthError(GenerationProviderRequestError):
    """The vendor rejected the configured credential itself (HTTP 401/403)
    — distinct from GenerationProviderNotConfiguredError, where no
    credential was set at all; here one is set but invalid/revoked/
    lacking access to the requested model."""

    error_type = "auth_error"


class GenerationProviderUnavailableError(GenerationProviderRequestError):
    """The vendor's service could not be reached or is erroring on its
    own side (network failure, timeout, 5xx) — not a problem with the
    request content or the credential."""

    error_type = "provider_unavailable"


def classify_http_error(status_code: int, response_text: str = "") -> type[GenerationProviderRequestError]:
    """Maps a vendor HTTP error response to the right GenerationProviderError
    subclass. Shared by every generation provider (image, video, and any
    future one) so this classification lives in exactly one place rather
    than being duplicated per-vendor or, worse, in a router."""
    if status_code == 429:
        return GenerationProviderQuotaExceededError
    if status_code in (401, 403):
        return GenerationProviderAuthError
    if status_code >= 500:
        return GenerationProviderUnavailableError
    lowered = response_text.lower()
    if any(term in lowered for term in ("insufficient_quota", "credit_balance_exhausted", "resource_exhausted", "quota")):
        return GenerationProviderQuotaExceededError
    return GenerationProviderRequestError
