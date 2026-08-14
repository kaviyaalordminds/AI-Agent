class GenerationProviderError(Exception):
    """Base class for audio/transcription/image/video/voice provider failures."""


class GenerationProviderNotConfiguredError(GenerationProviderError):
    """Raised when a generation capability isn't installed/configured on
    this machine. Callers surface this as a structured, honest status —
    never fall back to a fake or mocked result."""


class GenerationProviderRequestError(GenerationProviderError):
    """Raised when an otherwise-available provider's actual call fails."""
