"""Environment-driven application configuration.

All secrets and environment-specific values (database URL, session secret,
SMTP credentials, future provider credentials for Claude/Obsidian/MCP/etc.)
are read from environment variables / a .env file. Nothing here is
hard-coded, so a Development, Testing, Staging, or Production deployment is
selected purely through environment configuration.
"""
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import EmailStr, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "testing", "staging", "production"]
AIRuntimeMode = Literal["local", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Core ---
    app_name: str = "Shadow AI"
    app_env: Environment = "development"
    debug: bool = True
    api_prefix: str = "/api"
    # frontend_url is the PRIMARY frontend origin (used to build links in
    # emails, etc.) and drives resolved_cors_origins below (see main.py).
    # "localhost" and "127.0.0.1" are different *sites* (not just
    # origins) for cookie purposes, even though both point at the same
    # machine — session cookies are SameSite=Lax (see
    # app/security/sessions.py), so a mismatch between the frontend's own
    # origin and the host its JS calls the API on silently breaks login
    # (Set-Cookie accepted, but never sent back — see
    # frontend/assets/js/config.js for the full story). This no longer
    # requires picking one hostname and sticking to it everywhere:
    # config.js derives its apiBase from window.location.hostname, and
    # resolved_cors_origins (below) trusts both "localhost" and
    # "127.0.0.1" on this port — so the app works correctly opened at
    # either hostname, never mixed within one page load.
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
    # against the backend process's working directory. Only used when
    # obsidian_vault_path (below) is not set.
    obsidian_vault_root: str = "../storage/obsidian_vaults"
    # Optional override for single-user/personal deployments: point this
    # directly at a real, already-existing Obsidian vault (e.g.
    # "C:\Users\you\Documents\Obsidian Vault") and every user on this
    # backend operates on that exact directory directly — no per-user
    # UUID subfolder, no auto-provisioned scaffolding overwriting real
    # notes (see app/integrations/obsidian/factory.py: provisioning only
    # ever runs when the target directory doesn't already exist, so an
    # existing vault's folders/notes are never touched). This
    # deliberately trades away obsidian_vault_root's per-user isolation
    # — do not set this on a backend shared by more than one real user.
    # Leave unset (default) to keep the isolated-per-user architecture.
    obsidian_vault_path: str | None = None
    # Optional, purely informational identifier for the vault pointed at by
    # obsidian_vault_path — this is the same id Obsidian itself assigns a
    # vault the first time it's opened in the Obsidian app (visible in
    # Obsidian's own vault switcher / obsidian.json), not something this
    # backend invents. It is NOT used to locate or open the vault — the
    # filesystem path (obsidian_vault_path) is what every read/write
    # actually uses — but when the Obsidian desktop app's own config file
    # is readable on this machine, get_obsidian_provider() cross-checks
    # this id against it and surfaces a mismatch warning in the vault
    # status (see app/integrations/obsidian/vault_identity.py), so a
    # misconfigured path is caught rather than silently reading/writing
    # the wrong folder. When that file isn't reachable (e.g. this backend
    # runs somewhere other than the machine Obsidian is installed on) the
    # check is honestly reported as unverifiable, never as "verified".
    obsidian_vault_id: str | None = None

    # --- Audio / Transcription / Image / Video / Voice providers ---
    # Each is architected as interface + local/cloud factory + honest
    # capability detection. Image and video default to "cloud" (real,
    # API-key-based providers, no GPU/local model ever required or
    # installed) since this application is API-first for generation — image
    # uses OpenAI (see app/integrations/generation/image/openai_provider.py,
    # openai_api_key above), video uses Gemini/Veo (see
    # app/integrations/generation/video/gemini_provider.py, gemini_api_key
    # above). Audio/transcription/voice default to "local" (real local TTS
    # via espeak-ng for audio; a real cloud path exists for all three —
    # audio + transcription reuse openai_api_key above, voice cloning uses
    # elevenlabs_api_key below — set the provider to "cloud" once a key is
    # configured). See GET /api/system/capabilities for live status of
    # every provider.
    tts_provider: Literal["local", "cloud"] = "local"
    transcription_provider: Literal["local", "cloud"] = "local"
    image_provider: Literal["local", "cloud"] = "cloud"
    video_provider: Literal["local", "cloud"] = "cloud"
    voice_provider: Literal["local", "cloud"] = "local"

    # --- OpenAI audio (TTS) + transcription (Whisper) ---
    # Reuses openai_api_key above — the same OpenAI credential already
    # used for image generation also covers TTS (/v1/audio/speech) and
    # transcription (/v1/audio/transcriptions); no separate key needed.
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "alloy"
    openai_transcription_model: str = "whisper-1"

    # --- ElevenLabs voice cloning ---
    # A separate credential from OPENAI_API_KEY — OpenAI has no voice-
    # cloning endpoint, so cloning uses ElevenLabs specifically (the
    # most widely used voice-cloning API). Selected as the "cloud"
    # VOICE_PROVIDER once this key is set.
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_model: str = "eleven_multilingual_v2"

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
    # A production deployment swaps JOB_QUEUE=in_process for a persistent-
    # broker JobQueue implementation without changing job-creation call
    # sites — see app/jobs/queue.py.
    job_queue: Literal["in_process", "rq"] = "in_process"
    job_queue_max_workers: int = 4
    # Only read when job_queue == "rq": a Redis-backed (RQ) queue for true
    # multi-worker production scaling — submitted jobs survive an app
    # server restart/crash (they live in Redis, not this process's
    # memory) and any number of `python -m app.jobs.rq_worker` processes,
    # potentially on separate machines, can share the load. Requires a
    # reachable Redis instance and at least one worker process started
    # separately — see app/jobs/rq_worker.py and the README. Local
    # development can ignore both settings entirely; the default
    # in_process queue needs no extra infrastructure.
    redis_url: str = "redis://localhost:6379/0"
    rq_queue_name: str = "generation_jobs"

    # --- Email provider ---
    email_provider: Literal["console", "smtp"] = "console"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    email_from_address: EmailStr = "no-reply@ai-agent.dev"
    email_from_name: str = "Shadow AI"

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
    def resolved_cors_origins(self) -> list[str]:
        """The exact origin(s) CORSMiddleware trusts (see main.py) —
        never a wildcard, since allow_credentials=True requires an
        explicit list. If frontend_url's host is "localhost" or
        "127.0.0.1" (the two local-dev hostnames that are the same
        machine but different browser *origins*/*sites*), both variants
        are trusted on the same scheme/port so opening the app at either
        one works — frontend/assets/js/config.js derives its apiBase from
        window.location.hostname, so whichever one the frontend is opened
        at, it always calls the matching backend hostname, keeping every
        request same-site (SameSite=Lax cookies, see
        app/security/sessions.py). Any other configured host (a real
        deployment) is trusted as exactly the one origin given."""
        parsed = urlsplit(self.frontend_url)
        local_hosts = {"localhost", "127.0.0.1"}
        if parsed.hostname not in local_hosts:
            return [self.frontend_url]
        origins = []
        for host in local_hosts:
            netloc = f"{host}:{parsed.port}" if parsed.port else host
            origins.append(urlunsplit((parsed.scheme, netloc, "", "", "")))
        return origins

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
