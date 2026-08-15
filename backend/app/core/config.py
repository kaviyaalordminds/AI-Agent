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
    # frontend_url drives the CORS allow-list (see main.py) and MUST match
    # the exact origin the browser opens the frontend from — "localhost"
    # and "127.0.0.1" are different *sites* (not just origins) for cookie
    # purposes, even though both point at the same machine. This matters
    # a lot here: session cookies are SameSite=Lax (see
    # app/security/sessions.py), so if the frontend's own origin doesn't
    # match the host used for backend API calls, the browser silently
    # accepts the Set-Cookie on login and then refuses to attach it on
    # the very next request — login appears to succeed but immediately
    # bounces back to the login page. Keep this, frontend/assets/js/
    # config.js's apiBase, and whatever host you actually open the
    # frontend at, all using the SAME hostname (default: "localhost").
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    # --- Database (PostgreSQL) ---
    # 127.0.0.1 here is safe unlike the frontend/API host above: this is a
    # backend-internal Python-to-Postgres socket connection, never
    # browser-mediated, so there's no cookie/SameSite/CORS implication.
    # It avoids "localhost" resolution being slow on some Windows setups,
    # which can otherwise make every DB-backed request take many seconds.
    database_url: str = Field(
        default="postgresql+psycopg://ai_agent:ai_agent@127.0.0.1:5432/ai_agent_dev"
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
    # Governs *other* provider families' local-vs-cloud default (TTS/
    # transcription/image/video/voice each have their own local/cloud
    # setting below, e.g. IMAGE_PROVIDER) and is surfaced as informational
    # metadata by GET /api/system/capabilities. If unset, derived from
    # app_env (development/testing -> local, staging/production ->
    # production) by `resolved_ai_runtime_mode` below.
    #
    # It does NOT affect which AI chat/reasoning provider is used — that
    # is always Anthropic (Claude) unless AI_PROVIDER explicitly selects
    # "gemini". This application never uses Ollama or any local/self-hosted
    # LLM for chat/reasoning, in any mode.
    ai_runtime_mode: AIRuntimeMode | None = None
    # Explicit provider override. If unset, defaults to "anthropic" — see
    # resolved_ai_provider below.
    ai_provider: Literal["anthropic", "gemini"] | None = None

    # --- Claude provider (kept for backward compatibility; get_claude_provider()
    # now dispatches on ai_provider, see app/integrations/claude/factory.py) ---
    claude_provider: Literal["anthropic"] = "anthropic"
    anthropic_api_key: str | None = None
    claude_model: str = "claude-sonnet-5"
    claude_max_output_tokens: int = 4096

    # --- Gemini provider (alternative chat/reasoning provider to Anthropic;
    # also used for image/video media generation, see below) ---
    google_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    # --- Gemini media generation (video only — see openai_api_key below
    # for image) ---
    # A separate key name since Google issues API keys per-project and a
    # deployment may reasonably want to scope media generation separately
    # from text; GEMINI_API_KEY falls back to GOOGLE_API_KEY (see
    # resolved_gemini_api_key below) so setting only one is also fine.
    gemini_api_key: str | None = None
    # veo-2.0-generate-001 was retired / is no longer served by the Gemini
    # API's predictLongRunning endpoint (returns 404 "not found ... or is
    # not supported for predictLongRunning") — veo-3.1-generate-preview is
    # the currently supported model as of this writing, confirmed with a
    # real API key: the request is now accepted (a 429 quota/billing
    # response came back, not a 404 unknown-model response). Override via
    # GEMINI_VIDEO_MODEL if Google ships a newer one before this default
    # is updated again — do not revert to veo-2.0-generate-001, it is
    # confirmed gone from predictLongRunning.
    gemini_video_model: str = "veo-3.1-generate-preview"

    # --- OpenAI image generation ---
    # Provider name and credential are always separate values — OPENAI_API_KEY
    # is a credential, never a provider selector. IMAGE_PROVIDER (below)
    # picks "local" or "cloud"; when "cloud", this key is what the image
    # factory actually uses (see app/integrations/generation/image/factory.py).
    openai_api_key: str | None = None
    # dall-e-3 was rejected by a real account/key with "The model
    # 'dall-e-3' does not exist" (400, image_generation_user_error) —
    # gpt-image-1 is OpenAI's current image-generation model and the one
    # newer API keys/projects are provisioned against. Override via
    # OPENAI_IMAGE_MODEL if your account needs a different one (check
    # with GET https://api.openai.com/v1/models using your own key).
    openai_image_model: str = "gpt-image-1"

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
    # Each is architected as interface + local/cloud factory + honest
    # capability detection. Image and video default to "cloud" (real,
    # API-key-based providers, no GPU/local model ever required or
    # installed) since this application is API-first for generation — image
    # uses OpenAI (see app/integrations/generation/image/openai_provider.py,
    # openai_api_key above), video uses Gemini/Veo (see
    # app/integrations/generation/video/gemini_provider.py, gemini_api_key
    # above). Audio/transcription/voice default to "local" (real local TTS
    # via espeak-ng for audio; transcription/voice "cloud" remain
    # configuration points for a future vendor integration). See
    # GET /api/system/capabilities for live status of every provider.
    tts_provider: Literal["local", "cloud"] = "local"
    transcription_provider: Literal["local", "cloud"] = "local"
    image_provider: Literal["local", "cloud"] = "cloud"
    video_provider: Literal["local", "cloud"] = "cloud"
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
    def resolved_ai_provider(self) -> Literal["anthropic", "gemini"]:
        """Anthropic (Claude) is the default AI chat/reasoning provider in
        every runtime mode. Set AI_PROVIDER=gemini to use Gemini instead —
        there is no local/Ollama option."""
        return self.ai_provider or "anthropic"

    @property
    def resolved_gemini_api_key(self) -> str | None:
        return self.gemini_api_key or self.google_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
