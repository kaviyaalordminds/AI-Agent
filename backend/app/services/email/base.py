"""EmailProvider abstraction.

This is the first instance of the provider-abstraction pattern the whole
platform is built on (see project README, section "Provider Architecture").
Application code never talks to SMTP, a vendor SDK, or credentials
directly — it calls `EmailProvider.send(...)`, and `get_email_provider()`
decides which concrete implementation to construct from environment
configuration. Swapping providers (e.g. console -> SMTP -> a transactional
email API in production) never requires touching call sites.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None


class EmailProvider(ABC):
    @abstractmethod
    def send(self, message: EmailMessage) -> None:
        """Send an email. Must raise on failure — callers surface real errors,
        never a fake success."""
        raise NotImplementedError
