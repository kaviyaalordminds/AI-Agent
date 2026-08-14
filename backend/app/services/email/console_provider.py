import logging

from app.services.email.base import EmailMessage, EmailProvider

logger = logging.getLogger("email.console")


class ConsoleEmailProvider(EmailProvider):
    """Development-only provider: writes the email to the log instead of
    sending it, so signup/verification/reset flows are fully testable
    without real SMTP credentials. Never select this provider in staging or
    production (app startup enforces that)."""

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "\n----- EMAIL (console provider) -----\n"
            "To: %s\nSubject: %s\n\n%s\n-------------------------------------",
            message.to,
            message.subject,
            message.text_body,
        )
