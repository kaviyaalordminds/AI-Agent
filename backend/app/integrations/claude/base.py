"""ClaudeProvider abstraction.

Mirrors the EmailProvider pattern (see app/services/email/base.py):
application code never talks to the Anthropic SDK, an API key, or a model
name directly. It calls `ClaudeProvider.stream(...)`, and
`get_claude_provider()` decides which concrete implementation to build
from environment configuration. A production deployment can swap in a
different provider (a different vendor, a self-hosted model gateway, etc.)
without touching any call site.
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "assistant"]


@dataclass
class ClaudeMessage:
    role: Role
    content: str


@dataclass
class ProviderStatus:
    configured: bool
    provider: str
    model: str | None
    detail: str


class ClaudeProvider(ABC):
    @abstractmethod
    def status(self) -> ProviderStatus:
        """Real, current configuration status — never a cached guess."""
        raise NotImplementedError

    @abstractmethod
    def stream(
        self, messages: list[ClaudeMessage], system_prompt: str
    ) -> AsyncIterator[str]:
        """Yield response text deltas. Must raise ProviderRequestError (not
        return a fabricated response) if the underlying call fails."""
        raise NotImplementedError
