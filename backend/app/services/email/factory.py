from functools import lru_cache

from app.core.config import get_settings
from app.services.email.base import EmailProvider
from app.services.email.console_provider import ConsoleEmailProvider
from app.services.email.smtp_provider import SMTPEmailProvider


@lru_cache
def get_email_provider() -> EmailProvider:
    settings = get_settings()

    if settings.app_env in ("staging", "production") and settings.email_provider == "console":
        raise RuntimeError(
            "EMAIL_PROVIDER=console is not permitted in staging/production. "
            "Configure SMTP (or another real provider) via environment variables."
        )

    if settings.email_provider == "smtp":
        if not settings.smtp_host:
            raise RuntimeError(
                "EMAIL_PROVIDER=smtp requires SMTP_HOST (and typically SMTP_USERNAME/"
                "SMTP_PASSWORD) to be configured via environment variables."
            )
        return SMTPEmailProvider(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            from_address=settings.email_from_address,
            from_name=settings.email_from_name,
        )

    return ConsoleEmailProvider()
