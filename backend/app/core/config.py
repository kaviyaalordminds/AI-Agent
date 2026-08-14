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
AIRuntimeMode = Literal["local", "production"]


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

    # --- AI runtime mode ---
    # "local": prefer providers that need no cloud credentials (Ollama).
    # "production": prefer configured cloud providers. If unset, derived
    # from app_env (development/testing -> local, staging/production ->
    # production) by `resolved_ai_runtime_mode` below — so a bare
    # `APP_ENV=production` alone already does the right thing.
    ai_runtime_mode: AIRuntimeMode | None = None
    # Explicit provider override. If unset, derived from
    # resolved_ai_runtime_mode ("local" -> ollama, "production" -> anthropic).
    ai_provider: Literal["ollama", "anthropic", "gemini"] | None = None

    # --- Claude provider (kept for backward compatibility; get_claude_provider()
    # now dispatches on ai_provider/ai_runtime_mode, see app/integrations/claude/factory.py) ---
    claude_provider: Literal["anthropic"] = "anthropic"
    anthropic_api_key: str | None = None
    claude_model: str = "claude-sonnet-5"
    claude_max_output_tokens: int = 4096

    # --- Ollama provider (local mode default AI provider; no API key needed) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""  # must be set explicitly — no default model is assumed installed

    # --- Gemini provider (production-mode cloud alternative to Anthropic) ---
    google_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    # --- Storage provider ---
    storage_provider: Literal["local"] = "local"
    # Root directory generated assets (documents, images, etc.) are written
    # under, namespaced by category then user id. Relative paths are
    # resolved against the backend process's working directory.
    storage_root: str = "../storage"
    max_upload_file_size_mb: int = 25

    # --- Obsidian / Knowledge provider ---
    # `knowledge_provider` is the general-purpose name the platform
    # architecture exposes (capability API, docs); Obsidian is currently
    # the only implementation, so it drives obsidian_provider/
    # obsidian_vault_root directly. Each user gets their own vault under
    # {obsidian_vault_root}/{user_id}/ (see app/integrations/obsidian/factory.py)
    # — never one shared/global vault.
    knowledge_provider: Literal["obsidian"] = "obsidian"
    obsidian_provider: Literal["local_vault"] = "local_vault"
    # Root directory containing one vault subdirectory per user
    # ({obsidian_vault_root}/{user_id}/). Relative paths are resolved
    # against the backend process's working directory. Point this at a
    # real synced Obsidian vault location in production.
    obsidian_vault_root: str = "../storage/obsidian_vaults"

    # --- Audio / Transcription / Image / Video / Voice providers ---
    # These are architected (interface + factory + honest capability
    # detection) but only "local" has a real implementation attempt in
    # this deployment; "cloud" is a configuration point for a future
    # vendor integration. See app/integrations/{audio,transcription,image,
    # video,voice}/ and GET /api/system/capabilities.
    tts_provider: Literal["local", "cloud"] = "local"
    transcription_provider: Literal["local", "cloud"] = "local"
    image_provider: Literal["local", "cloud"] = "local"
    video_provider: Literal["local", "cloud"] = "local"
    voice_provider: Literal["local", "cloud"] = "local"

    # --- Deployment provider ---
    deployment_provider: Literal["local", "netlify", "vercel"] = "local"
    netlify_api_token: str | None = None
    vercel_api_token: str | None = None

    # --- Generation jobs / abuse protection (technical limits, not user credits) ---
    generation_rate_limit_max_requests: int = 20
    generation_rate_limit_window_minutes: int = 15
    generation_max_concurrent_jobs_per_user: int = 3
    generation_max_job_duration_seconds: int = 600
    # In-process worker pool size for JobQueue=in_process (local/dev default).
    # A production deployment swaps JOB_QUEUE=in_process for a Celery/RQ-
    # backed JobQueue implementation without changing job-creation call
    # sites — see app/jobs/queue.py.
    job_queue: Literal["in_process"] = "in_process"
    job_queue_max_workers: int = 4

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

    @property
    def resolved_ai_runtime_mode(self) -> AIRuntimeMode:
        if self.ai_runtime_mode is not None:
            return self.ai_runtime_mode
        return "production" if self.app_env in ("staging", "production") else "local"

    @property
    def resolved_ai_provider(self) -> Literal["ollama", "anthropic", "gemini"]:
        if self.ai_provider is not None:
            return self.ai_provider
        return "ollama" if self.resolved_ai_runtime_mode == "local" else "anthropic"


@lru_cache
def get_settings() -> Settings:
    return Settings()
