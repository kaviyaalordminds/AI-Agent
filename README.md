# AI Agent Platform

A full-stack AI Agent + Creative Studio + Obsidian Knowledge Intelligence
platform. This repository is being built in phases (see **Roadmap**
below); this README always reflects what's actually implemented, not the
full end-state vision.

## Runtime modes: local development vs. production

The same codebase supports two clearly separated runtime modes, switched
purely through environment configuration — no code changes required:

- **Local development / testing** (`AI_RUNTIME_MODE=local`, the default
  for `APP_ENV=development`/`testing`): prefers providers that need no
  cloud credentials. The default AI provider is **Ollama**
  (`AI_PROVIDER=ollama`) — install it locally and set `OLLAMA_MODEL`, or
  leave it unconfigured and every other feature still works, with AI
  features honestly reporting "not configured." See
  `.env.development.example`.
- **Production** (`AI_RUNTIME_MODE=production`, the default for
  `APP_ENV=staging`/`production`): prefers configured cloud providers —
  `AI_PROVIDER=anthropic` (Claude) or `AI_PROVIDER=gemini` are both real,
  working implementations selected purely by environment variable.
  Ollama also works in production if you're self-hosting a model server.
  See `.env.production.example`.

A single factory (`get_claude_provider()` in
`app/integrations/claude/factory.py` — kept under that name for backward
compatibility with every existing call site, but it is the platform's
general AI-provider factory, not Claude-specific) resolves
`AI_RUNTIME_MODE`/`AI_PROVIDER` into a concrete provider on every call.
**A missing or misconfigured AI provider never crashes the backend or
blocks unrelated features** — auth, projects, history, Obsidian,
Documents (listing/deleting), and every system/capability endpoint work
regardless; only the AI-dependent generation step inside AI Chat,
Knowledge Gaps, and Document drafting is gated, and it fails honestly
(persisting the user's input first) rather than faking a response.

This same local/production split applies to every other provider
category — see **Provider architecture** below — and is visible live at
runtime via `GET /api/system/capabilities` and the **System Status**
page (Settings → System Status, or the sidebar's own entry).

## What's implemented (Phase 1–7: Foundation, Authentication, Core UI, AI Agent, Obsidian, Knowledge Intelligence, Document Generation & Production-Ready Provider Architecture)

- **Backend**: FastAPI (Python), modular `app/` package (`api`, `models`,
  `schemas`, `security`, `services`, `database`, `core`).
- **Database**: PostgreSQL via SQLAlchemy 2.0 + Alembic migrations.
- **Auth**: email/password signup, email verification (one-time,
  expiring tokens), login, logout, logout-all-devices, forgot/reset
  password (one-time, expiring tokens, revokes all sessions), account
  lockout after repeated failed logins, DB-backed sessions (httponly
  cookie) with CSRF double-submit protection, Argon2id password hashing,
  rate limiting on auth-sensitive endpoints.
- **Profile & Settings**: name/email/password changes (email change
  re-verifies), active-session listing and per-session revocation,
  persisted theme/language/sidebar preferences.
- **Frontend**: HTML5 + CSS3 + Bootstrap 5 + vanilla JS (ES6+), no
  framework. Light/dark theme with persistence, responsive layout
  (desktop/tablet/mobile), collapsible sidebar, toasts, skeleton/empty/
  error states.
- **Projects**: create/rename/archive/unarchive/duplicate/delete, ownership-isolated
  per user, active/archived filtering, a per-project workspace with
  Overview/Chat/Knowledge/Files/Tasks/History/Settings tabs.
- **History**: a real, filterable, paginated activity log (type, status,
  project, search, date range) with rename/move-to-project/delete. It is
  legitimately empty until later phases start writing entries — nothing is
  seeded or faked.
- **Reusable workspace layout**: a full-screen toggle and a draggable,
  preset-snappable (40/60, 50/50, 60/40), per-instance-persisted
  split-screen component (`workspace-layout.js`/`.css`), demonstrated in
  the project workspace's Chat tab and ready for the AI Agent/Obsidian
  and Editor/Preview panes later phases will add.
- **AI Agent**: real Claude-backed chat — conversations with persisted
  message history, streaming responses (SSE), 7 modes (Chat, Knowledge,
  Create, Project, Research, Developer, Automation) each with a genuinely
  different system prompt, project-scoped conversations, auto-titling,
  and every completed/failed turn logged to History. A user's message is
  always persisted the instant it's sent, even if the assistant can't
  reply — nothing is silently lost.
- **ClaudeProvider abstraction**: `AnthropicApiProvider` (real Anthropic
  SDK, reads `ANTHROPIC_API_KEY`/`CLAUDE_MODEL`) is the second instance
  of the provider-abstraction pattern, alongside `EmailProvider`. **No
  Claude credentials are configured in this deployment's default
  environment** — see "Configuring a real Claude connection" below.
- **Obsidian integration**: a real, working vault per user — no Obsidian.app
  process or external credentials required, since a vault is just a folder
  of markdown files. `LocalVaultProvider` auto-provisions each user's vault
  (the spec's 00-System..09-AI-Memory folder structure + a welcome note) on
  first use, with full search/read/create/update/append/move/delete,
  real `[[wiki-link]]`/`#tag` parsing, and path-traversal protection. A
  vault browser page (create/edit/preview/move/delete notes) is in the
  sidebar. **Knowledge and Research chat modes now actually search the
  user's vault** and ground their replies in matching notes (basic
  keyword/token-overlap search — not semantic search or full gap/duplicate
  analysis, which are the Knowledge Intelligence phase) instead of saying
  "not built yet". Production points `OBSIDIAN_VAULT_ROOT` at a directory
  of real, synced per-user vaults instead of local storage.
- **Knowledge Intelligence**: a **Knowledge Center** page with a real,
  fully deterministic (no LLM) vault health dashboard — duplicate-note
  detection (identical/similar title, Jaccard-similarity content
  overlap), outdated-note detection (90-day staleness threshold),
  broken `[[wiki-link]]` detection, orphan-note detection (no incoming
  or outgoing links), a transparent/documented health-score formula, and
  a hand-rolled SVG knowledge graph (a small force-directed layout
  computed in plain JS — no charting library, no CDN). A **Knowledge
  Gaps** page runs Claude-backed gap analysis (spec's "what am I missing
  for a manufacturing HRMS system?" scenario) — it's gated by the same
  Claude configuration as AI Chat and follows the identical "never lose
  user input" contract: the query is always persisted, and if Claude
  isn't configured the analysis is honestly recorded as failed with the
  real error rather than silently dropped or faked. Every Obsidian note
  mutation (create/update/append/move/delete) is logged to History as a
  `knowledge_update` entry — surfaced as "Knowledge Updates" (a deep
  link into the existing History page, filtered) rather than a
  duplicate UI. A "Knowledge auto-update policy" preference
  (Auto/Approval/Smart Auto) is saved in Settings now, ready for the
  future capability (automatic vault updates proposed by gap analysis)
  that will read it.
- **Document Generation** (Phase 7's first Creative Studio module): a real
  **Documents** page drafts a document via Claude, then renders it to an
  actually-openable Markdown/.docx/.pdf file (`python-docx`/`reportlab` —
  real conversion, not a placeholder or renamed .txt) and stores it
  through the new `StorageProvider` abstraction. Gated by Claude
  configuration exactly like AI Chat and Knowledge Gaps: the prompt is
  always persisted first, and an unconfigured/failed Claude call is
  recorded honestly as a failed document with the real error rather than
  faked or dropped — **this module, and the rest of Phase 7, works fully
  whether or not `ANTHROPIC_API_KEY` is set; a missing key never blocks
  new phases, it only means document *drafting* itself stays gated until
  a real key is added.**
- **StorageProvider abstraction**: `LocalStorageProvider` (real files
  under `storage/`, category+owner-namespaced, path-traversal protected)
  is the first implementation — the interface is what Document Generation
  (and future Image/Video/Audio generation) writes through, so a future
  S3/GCS-backed provider drops in without touching call sites. Generated
  file references (never raw filesystem paths) are the only thing that
  ever reaches Postgres or the API response.
- **Ollama + Gemini AI providers**: alongside Anthropic, `OllamaProvider`
  (real local-model streaming via a running `ollama serve`, no API key)
  and `GeminiProvider` (real Google Gemini API access) both implement the
  same provider interface — switching between all three is a single
  `AI_PROVIDER` environment variable, no code changes.
- **Audio/Transcription/Image/Video/Voice provider architecture**: each
  is a real interface + local/cloud factory + honest capability
  detection (`GET /api/system/capabilities`) — never a fake "it works"
  status. **Local text-to-speech (Audio) is genuinely functional** via
  `espeak-ng`/`espeak` when installed (`LocalTTSProvider`, real WAV
  synthesis, no cloud key). Transcription/Image/Video/Voice honestly
  report "unavailable" locally in a typical CPU-only environment (no
  installed backend / no GPU+model checkpoint) with exact setup
  instructions — they never pretend to generate output they can't.
  Voice cloning requires an explicit consent confirmation before any
  provider call is attempted, and voice profiles are scoped per-user.
- **DeploymentProvider architecture**: `LocalDeploymentProvider` is real
  and working today — it zips a project's files and stores the archive
  via `StorageProvider` for download, no credentials required.
  `NetlifyProvider`/`VercelProvider` are real architecture points
  (config validation, honest "not configured" status) ready for a live
  vendor integration.
- **Generation job queue**: `GenerationJob` (Postgres-backed: id, user,
  project, type, provider, status, progress, input/output metadata,
  error, timestamps) + a `JobQueue` interface + `InProcessJobQueue` (a
  real asyncio-based local worker pool, no Redis/Celery required for
  local development, but interface-compatible with a future broker-backed
  queue). `POST /api/jobs/audio` exercises the full **Frontend → Create
  Job → Backend → Queue → Worker → Provider → Storage → Completed Job**
  pipeline for real, using local TTS. Concurrent-job-per-user and
  request-rate limits are enforced as technical abuse protection (not a
  credit system). Document generation intentionally stays synchronous
  (fast enough, and changing its API contract now would be a breaking
  change for no benefit) — the job queue is new infrastructure ready for
  Image/Video/Audio generation phases to build on.
- **`GET /health`** (bare liveness check) and **`GET /api/system/providers/health`**
  (deeper checks: database, AI provider — a real Ollama reachability
  ping in local mode, or configuration-level for cloud providers —
  Obsidian, storage, job queue) never expose secrets, only status/detail
  text.
- **No credit/usage-limit system** — by design, per the product spec.
  Rate limiting, concurrent-job limits, and file-size limits exist as
  technical infrastructure protection, configurable via environment
  variables (`GENERATION_RATE_LIMIT_MAX_REQUESTS`,
  `GENERATION_MAX_CONCURRENT_JOBS_PER_USER`, `MAX_UPLOAD_FILE_SIZE_MB`,
  etc.) — never a user-visible credit balance.
- **Provider-abstraction pattern**: `EmailProvider`, `ClaudeProvider`
  (now a general AI-provider factory), `ObsidianProvider`,
  `StorageProvider`, `DeploymentProvider`, and the five generation
  provider families establish the pattern the remaining MCP/website-
  generation integrations will follow — application code never talks to
  a vendor SDK, external API, or the filesystem directly.
- **AI Media + Document Generation** (Gemini Image/Video, Word/PPT/Excel):
  five new generation capabilities, each reusing existing architecture
  rather than duplicating it.
  - **Image generation**: `GeminiImageProvider` calls the Gemini API's
    Imagen models directly over `httpx` (no new SDK dependency — avoids
    the `google-genai` SDK's pydantic/httpx version conflicts identified
    earlier). `POST /api/generation/image` creates a `GenerationJob`,
    `GET /api/generation/image/{job_id}` polls status,
    `GET /api/generation/image/{job_id}/download` streams the result.
  - **Video generation**: `GeminiVideoProvider` drives the Gemini API's
    Veo models through their real async lifecycle — submit
    (`:predictLongRunning`) → poll the operation → download the finished
    file — which is genuinely long-running (minutes), so it always runs
    through the `GenerationJob` queue rather than blocking a request.
    Optional image-to-video via a base64-encoded reference image.
    Mirrors the image endpoints at `POST /api/generation/video`.
  - **Word/PowerPoint/Excel generation**: `POST /api/generation/document/
    {word,ppt,excel}` take fully structured content (no AI provider
    involved) — headings/paragraphs/bullet & numbered lists/tables for
    Word; title/subtitle/slides/bullets/speaker notes for PowerPoint;
    sheets/headers/rows/formulas/column widths/freeze panes/bar-line-pie
    charts for Excel — and render real, valid `.docx`/`.pptx`/`.xlsx`
    files via `python-docx`/`python-pptx`/`openpyxl`. These reuse the
    *existing* `Document` model/table and `/api/documents/{id}/download`
    endpoint (extended with two new `DocumentFormat` values, `pptx` and
    `xlsx`, via an `ALTER TYPE ... ADD VALUE` migration) rather than
    creating parallel tables/routes — a `Document` row doesn't care
    whether its content came from an AI draft or caller-supplied
    structure, only what format the result is. The AI-drafted
    `/api/documents` endpoint now rejects `pptx`/`xlsx` (422) since it
    has no logic to produce them from a free-text prompt — those formats
    only make sense via the structured endpoints.
  - Every one of the five generation actions is logged to History
    (`image`/`video`/`document` types, honest `completed`/`failed`
    status) and can optionally be associated with a project — exactly
    like every other generation path in this app. All nine endpoints
    require an authenticated session and CSRF on state-changing calls;
    the Gemini API key is read only from backend environment variables
    (`GEMINI_API_KEY`, falling back to `GOOGLE_API_KEY`) and is never
    sent to or reachable from the frontend — the frontend only ever
    calls this backend, never the Gemini API directly.
  - **Frontend**: five new pages (`image-generation.html`,
    `video-generation.html`, `word-generation.html`, `ppt-generation.html`,
    `excel-generation.html`) reusing the existing design system (`surface`,
    `btn-brand`, `form-control-premium`, `badge-pill`, `empty-state`,
    dark/light theme) rather than introducing a new one — plain HTML5 +
    Bootstrap 5 + vanilla JS, no framework. Image/video pages show live
    job progress (queued → processing → completed/failed) and a
    capability banner when the configured provider is unavailable; Word/
    PPT/Excel pages are structured content editors (block/slide/sheet
    builders, including a real add/remove-row/column spreadsheet grid
    and per-sheet chart configuration). All five are wired into the
    sidebar nav and the dashboard's quick-create tiles.

Everything above is fully wired end-to-end (frontend ↔ backend ↔
database ↔ Claude API ↔ vault filesystem) and covered by an automated
test suite — nothing here is a mockup or placeholder.

### What you'll see marked "planned for a later phase"

The sidebar, dashboard quick-create tiles, and Settings tabs for
Image/Video/Audio/Website/Design studios and Deployments are visibly
present (matching the target navigation structure) but intentionally
disabled — clicking them shows an honest "planned for a later
development phase" message instead of a fake result. (Knowledge Center,
Knowledge Gaps, and Knowledge Updates are real and enabled as of Phase
6; Documents is real and enabled as of Phase 7 — see above.) Within AI
Chat and the project workspace's Chat tab, each mode's
system prompt is explicit about which of its described capabilities
(full knowledge-gap analysis, generation tools, code execution,
multi-step tool orchestration) aren't wired up yet, rather than the
agent claiming to have done something it didn't. This is deliberate:
the product spec explicitly forbids fake success states, so until a
module has a real backend behind it, its UI (or the agent itself) says
so rather than pretending.

### Configuring an AI provider (Ollama, Claude, or Gemini)

This deployment's default local environment has no cloud API key
configured, so `/api/agent/status` honestly reports "not configured" and
every chat/gap-analysis/document-drafting request gets a clear,
actionable error instead of a fabricated reply. Three real providers are
available — pick one via `AI_PROVIDER`:

```bash
# backend/.env — Option 1: Ollama (local, no API key)
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1          # any model you've `ollama pull`ed

# Option 2: Anthropic Claude
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-5    # optional, this is the default

# Option 3: Google Gemini
AI_PROVIDER=gemini
GOOGLE_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash   # optional, this is the default
```

Restart the backend — no code changes required for any of the three.
The Settings → AI Provider tab, the dashboard's connection widget, and
`GET /api/system/capabilities` all reflect the real status immediately.
AI Chat, Knowledge Gaps, and Documents all reuse this exact same
provider and configuration — no separate credential is needed per
feature.

**A missing/unconfigured AI provider never blocks development of new
phases or crashes the backend.** The provider is constructed lazily,
inside a `try/except ProviderNotConfiguredError`, at the one call site
each feature needs it — never at app startup — so the backend always
starts cleanly and every other module (auth, projects, history,
Obsidian, Knowledge Intelligence, Documents listing, Storage, Jobs,
System Status) works fully regardless of the AI provider's configuration
state. Only the actual drafting/generation step inside AI Chat,
Knowledge Gaps, and Documents is gated, and it fails honestly
(persisting the user's input first) rather than faking a response.

### Connecting a real Obsidian vault

Unlike Claude, Obsidian works out of the box with no credentials — each
user's vault is auto-created at `{OBSIDIAN_VAULT_ROOT}/{user_id}/` on
first use. To point a user's account at a real, already-existing
Obsidian vault (e.g. one synced via Obsidian Sync, iCloud, or Syncthing)
instead of local storage:

```bash
# backend/.env
OBSIDIAN_VAULT_ROOT=/path/to/a/directory/containing/one/vault/per/user
```

The directory layout is `{OBSIDIAN_VAULT_ROOT}/{user_id}/` — for a
single-user deployment you'd point a user's folder directly at their
real vault. This is the same provider-abstraction pattern as Claude and
email: `ObsidianProvider` is an interface, `LocalVaultProvider` is
today's (fully functional) implementation, and a future MCP- or REST
API-backed provider could be swapped in via `OBSIDIAN_PROVIDER` without
touching call sites.

### Configuring local generation capabilities (audio/transcription/image/video)

Check what's actually available on your machine at
`GET /api/system/capabilities` or the **System Status** page — it's real
detection, never a hard-coded "working" state:

- **Audio (text-to-speech)** — install `espeak-ng` (`apt install
  espeak-ng` on Linux, `brew install espeak-ng` on macOS) and it works
  immediately with `TTS_PROVIDER=local`, no restart-required config
  beyond having the binary on `PATH`.
- **Transcription** — install a local Whisper backend
  (`pip install faster-whisper` is recommended; no ffmpeg required) with
  `TRANSCRIPTION_PROVIDER=local`.
- **Image / Video** — no bundled local backend; these realistically need
  a GPU and multi-GB model checkpoints this application does not ship,
  so `IMAGE_PROVIDER=local`/`VIDEO_PROVIDER=local` (the default) reports
  an honest "unavailable" status with exact reasons. Set
  `IMAGE_PROVIDER=cloud`/`VIDEO_PROVIDER=cloud` plus `GEMINI_API_KEY`
  (or `GOOGLE_API_KEY`) to switch to the real `GeminiImageProvider`
  (Imagen)/`GeminiVideoProvider` (Veo) — see "AI Media + Document
  Generation" above and `GEMINI_IMAGE_MODEL`/`GEMINI_VIDEO_MODEL` in
  `.env.example` for the model names.
- **Voice cloning** — no bundled local backend and no cloud provider
  implemented yet; `VOICE_PROVIDER=cloud` reports honest "unavailable"
  until a real vendor integration lands (architecture point — see
  `app/integrations/generation/voice/cloud_provider.py`).

## Architecture

```
backend/
  app/
    main.py            FastAPI app, CORS, error handlers, router mounting
    core/               settings (env-driven), logging
    database/            SQLAlchemy engine/session, declarative base
    models/              User, UserSession, UserSettings, EmailVerificationToken,
                          PasswordResetToken, Project, HistoryEntry,
                          Conversation, Message, KnowledgeAnalysis, Document,
                          GenerationJob
    schemas/              Pydantic request/response models + validation
    security/             Argon2id hashing, token generation/hashing,
                          session + CSRF dependencies, rate limiting
    services/email/       EmailProvider abstraction (console/SMTP + factory)
    integrations/
      claude/               general AI-provider factory (kept under this name
                            for backward compat): AnthropicApiProvider,
                            OllamaProvider, GeminiProvider + utils.complete()
                            shared stream-to-string helper
      obsidian/              ObsidianProvider/KnowledgeProvider abstraction
                            (LocalVaultProvider, markdown tag/link parsing,
                            path-safety + factory; get_knowledge_provider alias)
      storage/               StorageProvider abstraction (LocalStorageProvider,
                            category+owner-namespaced, path-safety, file-size
                            limit + factory)
      deployment/            DeploymentProvider abstraction (LocalDeploymentProvider
                            — real zip packaging via StorageProvider —,
                            NetlifyProvider/VercelProvider architecture points)
      generation/            errors.py (shared GenerationProviderError hierarchy)
                            + audio/ (AudioProvider: LocalTTSProvider — real
                            espeak-ng synthesis —, CloudTTSProvider)
                            + transcription/ (TranscriptionProvider: LocalWhisperProvider,
                            CloudTranscriptionProvider)
                            + image/, video/, voice/ (same local/cloud pattern,
                            honest capability() detection throughout)
      capability.py           shared CapabilityStatus shape every provider
                            family reports through GET /api/system/capabilities
    agents/                per-mode system prompts + orchestrator (chat turn:
                          persist -> build context (project + vault search for
                          Knowledge/Research modes) -> stream -> persist -> log)
    knowledge/             vault_analysis.py (deterministic duplicate/outdated/
                          broken-link/orphan detection, health score, graph
                          builder), gap_analysis.py (Claude-backed gap analysis,
                          same never-lose-input contract as agents/)
    documents/              generator.py (AI-drafted content -> render ->
                          StorageProvider, same never-lose-input contract),
                          render.py (real markdown -> docx/pdf conversion),
                          structured.py (structured/non-AI content -> render
                          -> StorageProvider, same Document table),
                          structured_render.py (real docx/pptx/xlsx
                          rendering via python-docx/python-pptx/openpyxl)
    jobs/                   queue.py (JobQueue interface), in_process_queue.py
                          (real asyncio worker pool, Celery/RQ-swappable),
                          worker.py (Provider -> Storage -> job-row dispatcher
                          for audio/transcription/image/video job types),
                          service.py (shared create/lookup/download logic
                          used by both /api/jobs/* and /api/generation/*)
    api/
      auth/               /api/auth/* routes
      users/              /api/users/* routes
      projects/            /api/projects/* routes
      history/              /api/history/* routes
      agent/                /api/agent/* routes (conversations, SSE chat, status)
      obsidian/              /api/obsidian/* routes (notes CRUD, search, status)
      knowledge/             /api/knowledge/* routes (health, graph, gap analyses)
      documents/              /api/documents/* routes (create/list/get/download/delete)
      generation/             /api/generation/* routes (image/video jobs;
                            structured word/ppt/excel document generation)
      jobs/                   /api/jobs/* routes (create audio job, list/get/
                            cancel/download; concurrency + rate limiting)
      system/                 /api/system/capabilities, /api/system/providers/health
  alembic/                DB migrations
  tests/                  pytest suite (256 tests, real Postgres, no mocks)

frontend/
  index.html              session-aware redirect (dashboard vs login)
  pages/                  login, signup, forgot/reset password, verify-email,
                          dashboard, profile, settings, projects,
                          project-workspace, history, agent (AI Chat),
                          obsidian (vault browser), knowledge (Knowledge
                          Center), knowledge-gaps (Knowledge Gaps), documents
                          (Documents Studio), system-status (capabilities +
                          component health), image-generation, video-generation,
                          word-generation, ppt-generation, excel-generation
  assets/
    css/                  design tokens (theme.css), auth layout, app shell,
                          workspace-layout.css (full-screen/split-screen),
                          agent.css (chat UI), obsidian.css (vault browser),
                          knowledge.css (health dashboard, SVG graph, gap results),
                          documents.css (draft form, format picker, file list),
                          system-status.css (capability cards, health rows),
                          media-generation.css (image/video job progress +
                          preview frame, structured Word/PPT/Excel editors)
    js/                   api client (aiProviderLabel() maps the configurable
                          AI_PROVIDER to a display name — never hard-codes
                          "Claude"), theme, toast, nav/shell, generic confirm
                          modal, reusable split-screen/full-screen controller,
                          shared history-row renderer, SSE chat client,
                          minimal safe markdown preview renderer, force-directed
                          SVG knowledge graph renderer, system-status.js
                          (shared capability-grid/health-list renderer, used by
                          both the standalone page and the Settings tab),
                          generation-common.js (shared job polling/status
                          badges/project-picker used by the five new
                          generation pages), image-generation.js,
                          video-generation.js, word-generation.js,
                          ppt-generation.js, excel-generation.js, page
                          controllers
    vendor/                vendored Bootstrap 5 + Bootstrap Icons (no CDN
                          dependency — see below)
  components/             (reserved for shared HTML fragments as the app grows)

storage/
  obsidian_vaults/         default per-user vault root (see "Connecting a
                          real Obsidian vault" above)
  documents/{user_id}/…    real generated .md/.docx/.pdf files, written
                          through StorageProvider (Phase 7)
  generated_audio/{user_id}/…  real .wav files from audio generation jobs
  deployments/{user_id}/…  real .zip archives from LocalDeploymentProvider
  images/videos/…          generated-asset roots for Image/Video generation
                          once a real local/cloud backend is configured,
                          same StorageProvider
docker-compose.yml        local PostgreSQL for development
```

**Why vendored Bootstrap instead of a CDN `<link>`?** Some network
environments (including the one this was built in) block CDN hosts like
`cdn.jsdelivr.net` outright. A production app that hard-depends on a
third-party CDN for its CSS framework is one blocked request away from
rendering unstyled. Bootstrap 5.3.3 and Bootstrap Icons 1.11.3 are
vendored under `frontend/assets/vendor/` (~700KB) instead.

### Hybrid storage model (per spec)

- **PostgreSQL** — users, sessions, tokens, projects, chat history,
  generation history, and (as of Phase 7) `documents` rows: prompt,
  drafted content, status/error, and a `StorageProvider` reference —
  never the file's bytes.
- **Filesystem (`storage/`)**, via `StorageProvider` — the actual
  generated binary assets (currently: generated documents). Postgres
  stores a reference, never the blob.
- **Obsidian** — the knowledge layer: notes, research, project
  documentation, AI memory. Never used as a database substitute.

### Provider abstraction / credential-agnosticism

`app/services/email/` is the template every future integration
(`ClaudeProvider`, `ObsidianProvider`, `MCPProvider`, `StorageProvider`,
`DeploymentProvider`) will follow: an abstract interface, one or more
concrete implementations, and a factory that selects/configures the
implementation from environment variables. Application code depends only
on the interface. Swapping a development credential for a production one
never requires touching call sites — only environment configuration
changes. `EMAIL_PROVIDER=console` (the dev default) is refused at startup
if `APP_ENV` is `staging` or `production`, so a real provider can't be
silently skipped in a real deployment.

## Running locally

### Backend

**macOS/Linux:**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Postgres: either `docker compose up -d` from the repo root, or point
# DATABASE_URL at any local/remote Postgres instance.
cp .env.development.example .env   # or .env.production.example for prod; edit as needed

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**Windows:**

```bat
cd backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

copy .env.development.example .env
alembic upgrade head
py -m uvicorn app.main:app --reload --port 8000
```

Local development works with **zero cloud API keys** — the default
`.env.development.example` targets Ollama (optional; the backend starts
and every non-AI feature works even without it installed — see
**Runtime modes** above). XAMPP or another local Windows LAMP/WAMP-style
stack is *not* required or assumed anywhere in this codebase; Postgres
via `docker-compose.yml` (or any reachable Postgres instance) plus a
plain Python virtualenv is the full local dependency set on any OS.

API docs: http://localhost:8000/api/docs (disabled in production).

### Frontend

Plain HTML5/CSS3/Bootstrap 5/vanilla JavaScript — no npm/Vite/build step
exists or is required. Serve the static files with any static server:

```bash
cd frontend
python3 -m http.server 5173      # macOS/Linux
py -m http.server 5173           # Windows
```

Open http://localhost:5173. The frontend calls the backend at
`http://localhost:8000/api` by default (see `frontend/assets/js/config.js`
to override for a different backend origin).

**Note:** the backend's CORS allowlist is `FRONTEND_URL` from `.env`
(default `http://localhost:5173`) — the origin you open the frontend
from must match exactly (`localhost`, not `127.0.0.1`, unless you change
both).

### Tests

```bash
cd backend
.venv/bin/pytest tests/ -v
```

256 tests covering signup, duplicate-email/weak-password/mismatch
rejection, email verification (incl. single-use/expiry), login (incl.
unverified-account block, wrong password, account lockout), logout,
logout-all, per-session revocation, forgot/reset password (incl.
single-use tokens and session revocation on reset), profile updates,
email change, password change, settings persistence, project CRUD
(create/rename/archive/unarchive/duplicate/delete), cross-user project
ownership isolation, history listing/filtering/pagination/rename/
move/delete, the AI Agent module (conversation CRUD, cross-user
isolation, streamed chat against a fake deterministic provider,
project-context injection into the system prompt, history logging on
both success and failure, and a regression test proving a user's
message is persisted even when Claude isn't configured), the Obsidian
module (vault auto-provisioning, full note CRUD, path-traversal
rejection, folder/keyword search and ranking, cross-user vault
isolation, and — using the same fake-provider pattern as the Claude
tests — that Knowledge/Research mode chat turns actually inject matching
vault content into the system prompt while Chat mode does not), and the
Knowledge Intelligence module (duplicate/outdated/broken-link/orphan
detection correctness against constructed vault fixtures, the health-
score formula's penalty/cap behavior, knowledge-graph node/edge
construction incl. bidirectional-edge dedup, the `/api/knowledge/health`
and `/api/knowledge/graph` endpoints reflecting real vault state, Obsidian
mutations logging real `knowledge_update` History entries, and gap
analysis's honest not-configured path plus a fake-provider structured-
response-parsing path proving the query is never lost even when the
in-stream call fails), and the Document Generation module
(`LocalStorageProvider` write/read/delete round-trips, path-traversal
rejection, per-owner isolation on disk; the markdown block parser and
real docx/pdf rendering, including empty-content edge cases; and the
`/api/documents/*` endpoints' honest not-configured path, a fake-provider
success path verified for all three formats — markdown, real .docx
zip/PDF magic bytes — download content-type/filename correctness,
cross-user ownership isolation, and `document` History logging), the AI
provider architecture (`resolved_ai_runtime_mode`/`resolved_ai_provider`
mode-derivation logic, Ollama's not-configured and — a real network call
against an intentionally-unreachable local port — unreachable-server
paths, Gemini's not-configured path, an unknown-provider-name fallback),
the five generation provider families (real local audio synthesis via
`espeak-ng` producing an actual playable WAV, and the honest
"unavailable"/not-configured contract for transcription/image/video/
voice — including voice cloning's consent-required check), the
DeploymentProvider (`LocalDeploymentProvider` producing a real, openable
zip archive; Netlify/Vercel's honest not-configured paths), the
generation job queue (`POST /api/jobs/audio` exercising the complete
real Frontend→Job→Queue→Worker→Provider→Storage→Completed pipeline
against a real local TTS backend — no mocking — plus download,
cancellation, the 409 "already terminal" contract, per-user concurrency
limits, cross-user isolation, History logging, and a fake-provider test
proving a job that fails lands on `failed` with a real error rather than
fabricating success), and the system Capability/Health APIs
(`/api/system/capabilities` reporting all ten categories with real
status, `/api/system/providers/health` covering database/AI
provider/Obsidian/storage/job-queue, and a regression test proving
neither endpoint ever leaks a configured secret into its response), and
the AI Media + Document Generation module (`test_media_generation.py`:
image/video job creation, validation, auth/CSRF enforcement, the honest
not-configured failure path with no real Gemini call, a fake-provider
success path proving the complete job pipeline and download work,
reference-image-to-video handling, project association, cross-user
isolation, History logging, and — for Word/PPT/Excel — real file
generation verified via ZIP structure/magic bytes (`word/document.xml`,
`ppt/slides/slideN.xml`, `xl/worksheets/sheet1.xml`, real chart XML for
the Excel chart path), plus a regression test proving the AI-drafted
`/api/documents` endpoint correctly rejects `pptx`/`xlsx`) — all
against a real PostgreSQL test database and a real (temp-directory)
filesystem vault/storage root, no mocked ORM and no mocked filesystem.

There is deliberately no test that calls a real Anthropic, Gemini, or
Ollama API over the network: this deployment's test environment pins
`AI_PROVIDER=anthropic` with no `ANTHROPIC_API_KEY` configured (see
"Configuring an AI provider" above), and the honest "not configured"
path is exactly what's under test — except for the one real Ollama
reachability check, which deliberately targets `localhost:11434` (no
server there in CI) to prove the "provider unreachable" failure path is
genuine, not mocked.

## Production deployment

The target production architecture is:

```
Frontend hosting (static: Bootstrap/vanilla JS — any CDN/static host)
  +
FastAPI backend (this repo's backend/, run under a real ASGI server —
  e.g. uvicorn behind a reverse proxy, or gunicorn+uvicorn workers)
  +
PostgreSQL (managed or self-hosted; DATABASE_URL points at it)
  +
Object storage (S3-compatible — swap StorageProvider's implementation;
  LocalStorageProvider also works in production for a single-instance
  deployment, it's just not horizontally scalable across machines)
  +
Job queue (swap JobQueue's implementation for a Celery/RQ/Dramatiq-backed
  one once real Image/Video generation needs true multi-process/multi-
  machine workers; InProcessJobQueue is genuinely fine for a single-
  instance deployment's current job types)
  +
Workers (optionally GPU-backed, once local Image/Video/Voice generation
  backends are configured)
  +
External AI providers (Anthropic/Gemini in production mode, or a
  self-hosted Ollama server reachable from the backend)
```

This is deliberately **not** designed around one developer's machine —
every provider category is swappable via environment configuration
(see **Runtime modes** above), and nothing assumes XAMPP, a Windows-only
toolchain, or a single always-on developer laptop. `docker-compose.yml`
in this repo provisions Postgres for local development only; a real
deployment supplies its own managed Postgres, object storage, and
(eventually) queue infrastructure via `DATABASE_URL`, `STORAGE_*`, and
`JOB_QUEUE*` environment variables — `.env.production.example` is the
starting point. No application code changes are required to move from
the local single-file-server setup to this architecture; only
configuration and (for object storage / a real queue) new
`StorageProvider`/`JobQueue` implementations behind the existing
interfaces.

## Roadmap

This repo follows the phased plan from the product spec:

1. ✅ **Foundation** — repo structure, backend/frontend skeleton, Postgres, env config
2. ✅ **Authentication** — signup/login/verify/reset/sessions/profile
3. ✅ **Core UI** — reusable full-screen/split-screen workspace shell, history, projects UI
4. ✅ **AI Agent** — AI provider architecture (Ollama/Anthropic/Gemini, mode-aware factory), orchestrator, chat, streaming, 7 modes (tool-calling architecture still to come)
5. ✅ **Obsidian** — per-user vault (never a shared/global one), search/read/create/update/append/move/delete/get_metadata, connection status, Knowledge/Research mode grounding (MCP/REST bridge to a live Obsidian.app instance is a possible future provider — the current one operates directly on vault files, which is what a live Obsidian instance is backed by anyway)
6. ✅ **Knowledge Intelligence** — gap/duplicate/outdated/broken-link/orphan detection, health score, knowledge graph, AI-backed gap analysis, knowledge-update history, auto-update policy setting (Auto/Approval/Smart Auto — saved now, ready for the future automatic-apply capability)
7. 🟡 **Creative tools** — image/audio/video/document/design generation. **Document generation is done**: AI-drafted content rendered to real Markdown/.docx/.pdf via `StorageProvider`, gated honestly by AI provider configuration. **Structured Word/PowerPoint/Excel generation is done**: `POST /api/generation/document/{word,ppt,excel}` render real .docx/.pptx/.xlsx files from caller-supplied structured content (headings/paragraphs/lists/tables; slides/bullets/notes; sheets/rows/formulas/charts) via `python-docx`/`python-pptx`/`openpyxl` — no AI provider required. **Local audio (TTS) generation is done**: real `espeak-ng`-backed synthesis through the job queue (`POST /api/jobs/audio`). **Image and video generation via Gemini are done**: `GeminiImageProvider` (Imagen `:predict`) and `GeminiVideoProvider` (Veo `:predictLongRunning` + poll + download) are real REST-based providers, selected when `GEMINI_API_KEY`/`GOOGLE_API_KEY` + `IMAGE_PROVIDER=cloud`/`VIDEO_PROVIDER=cloud` are configured; both run through the `GenerationJob` queue (`POST /api/generation/image`, `POST /api/generation/video`) with real status polling and download. Full provider architecture (interface + local/cloud factory + honest capability detection) exists for all five generation categories (Audio/Transcription/Image/Video/Voice) plus Deployment — Transcription/Voice cloning remain ⬜ for actual generation (each needs a real backend/GPU/model or a real external vendor integration), but report exactly why via `GET /api/system/capabilities` rather than pretending to work. Website/3D Website/Poster/Logo/Graphic Design generation itself remain ⬜.
8. 🟡 **Developer Studio** — website/3D website generation, live preview, deployment. **Deployment architecture is done**: `DeploymentProvider` (`LocalDeploymentProvider` — real zip packaging, no credentials — plus Netlify/Vercel architecture points) is ready for website generation to use once built; website generation itself remains ⬜.
9. 🟡 **Integration** — projects ↔ knowledge ↔ history ↔ files ↔ AI context ↔ activity log. **Production-readiness architecture landed this phase**: local/production runtime-mode switching (`AI_RUNTIME_MODE`), a real generation job queue (`GenerationJob` + `JobQueue` + `InProcessJobQueue`, Celery/RQ-swappable), the Capability API (`GET /api/system/capabilities`) and Health API (`GET /health`, `GET /api/system/providers/health`), a System Status frontend page + Settings tabs, and technical rate-limiting/concurrency/upload-size protection (no user-visible credit system). Remaining integration work: wiring future Image/Video generation through the job queue, and a persistent-broker `JobQueue` implementation for true multi-worker production scaling.
10. ⬜ **Testing** — expanded integration/E2E/security test coverage
11. ⬜ **Final polish** — performance, accessibility, full responsive/theme QA

Each phase is expected to land as real, working, end-to-end functionality
— never a UI-only mockup — consistent with the project's "no placeholder
functionality" rule.
