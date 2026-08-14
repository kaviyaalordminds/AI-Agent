from app.core.config import get_settings
from app.services.email.base import EmailMessage

settings = get_settings()


def verification_email(to: str, full_name: str, token: str) -> EmailMessage:
    link = f"{settings.frontend_url}/pages/verify-email.html?token={token}"
    text = (
        f"Hi {full_name},\n\n"
        f"Welcome to {settings.app_name}. Please verify your email address by "
        f"visiting the link below:\n\n{link}\n\n"
        f"This link expires in {settings.email_verification_token_ttl_hours} hours. "
        f"If you did not create this account, you can ignore this email."
    )
    return EmailMessage(to=to, subject=f"Verify your {settings.app_name} account", text_body=text)


def password_reset_email(to: str, full_name: str, token: str) -> EmailMessage:
    link = f"{settings.frontend_url}/pages/reset-password.html?token={token}"
    text = (
        f"Hi {full_name},\n\n"
        f"We received a request to reset your {settings.app_name} password. "
        f"Visit the link below to choose a new password:\n\n{link}\n\n"
        f"This link expires in {settings.password_reset_token_ttl_minutes} minutes and can "
        f"only be used once. If you did not request this, you can safely ignore this email — "
        f"your password will not be changed."
    )
    return EmailMessage(to=to, subject=f"Reset your {settings.app_name} password", text_body=text)
