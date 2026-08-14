"""Environment-driven application configuration.

All secrets and environment-specific values (database URL, session secret,
SMTP credentials, future provider credentials for Claude/Obsidian/MCP/etc.)
are read from environment variables / a .env file. Nothing here is
hard-coded, so a Development, Testing, Staging, or Production deployment is
selected purely through environment configuration.
"""
from functools import lru_cache
from typing import Literal

from pydantic import EmailStr, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "testing", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Core ---
    app_name: str = "AI Agent Platform"
    app_env: Environment = "development"
    debug: bool = True
    api_prefix: str = "/api"
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    # --- Database (PostgreSQL) ---
    database_url: str = Field(
        default="postgresql+psycopg://ai_agent:ai_agent@localhost:5432/ai_agent_dev"
    )

    # --- Security / Sessions ---
    secret_key: str = Field(default="dev-insecure-secret-change-me")
    session_cookie_name: str = "aiagent_session"
    csrf_cookie_name: str = "aiagent_csrf"
    session_ttl_hours: int = 24 * 14
    session_cookie_secure: bool = False  # must be true in staging/production (HTTPS)
    password_reset_token_ttl_minutes: int = 30
    email_verification_token_ttl_hours: int = 48

    # --- Rate limiting (auth-sensitive endpoints) ---
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    rate_limit_window_minutes: int = 15
    rate_limit_max_requests: int = 10

    # --- Claude provider ---
    claude_provider: Literal["anthropic"] = "anthropic"
    anthropic_api_key: str | None = None
    claude_model: str = "claude-sonnet-5"
    claude_max_output_tokens: int = 4096

    # --- Email provider ---
    email_provider: Literal["console", "smtp"] = "console"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    email_from_address: EmailStr = "no-reply@ai-agent.dev"
    email_from_name: str = "AI Agent Platform"

    @field_validator("session_cookie_secure", mode="after")
    @classmethod
    def _enforce_secure_cookie_in_prod(cls, v: bool, info):
        env = info.data.get("app_env")
        if env in ("production", "staging") and not v:
            return True
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
