# AI Agent Platform

A full-stack AI Agent + Creative Studio + Obsidian Knowledge Intelligence
platform. This repository is being built in phases (see **Roadmap**
below); this README always reflects what's actually implemented, not the
full end-state vision.

## What's implemented (Phase 1–7: Foundation, Authentication, Core UI, AI Agent, Obsidian, Knowledge Intelligence & Document Generation)

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
- **No credit/usage-limit system** — by design, per the product spec.
- **Provider-abstraction pattern**: `EmailProvider`, `ClaudeProvider`,
  `ObsidianProvider`, and `StorageProvider` establish the pattern the
  remaining MCP/Image/Video/Audio/Deployment integrations will follow —
  application code never talks to a vendor SDK, external API, or the
  filesystem directly.

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

### Configuring a real Claude connection

This deployment's default environment has no `ANTHROPIC_API_KEY`, so
`/api/agent/status` honestly reports "not configured" and every chat
message gets a clear, actionable error instead of a fabricated reply.
To connect a real account:

```bash
# backend/.env
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-5   # optional, this is the default
```

Restart the backend — no code changes required. The Settings → Claude
tab and the dashboard's Claude Connection widget both reflect the real
status immediately. The Knowledge Gaps and Documents pages reuse this
exact same provider and configuration — no separate credential is
needed for gap analysis or document drafting.

**A missing `ANTHROPIC_API_KEY` never blocks development of new
phases.** The provider is constructed lazily, inside a `try/except
ProviderNotConfiguredError`, at the one call site each feature needs it
— never at app startup — so the backend always starts cleanly and every
other module (auth, projects, history, Obsidian, Knowledge Intelligence,
Documents) works fully regardless of Claude's configuration state. Only
the actual drafting/generation step inside AI Chat, Knowledge Gaps, and
Documents is gated, and it fails honestly (persisting the user's input
first) rather than faking a response.

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

## Architecture

```
backend/
  app/
    main.py            FastAPI app, CORS, error handlers, router mounting
    core/               settings (env-driven), logging
    database/            SQLAlchemy engine/session, declarative base
    models/              User, UserSession, UserSettings, EmailVerificationToken,
                          PasswordResetToken, Project, HistoryEntry,
                          Conversation, Message, KnowledgeAnalysis, Document
    schemas/              Pydantic request/response models + validation
    security/             Argon2id hashing, token generation/hashing,
                          session + CSRF dependencies, rate limiting
    services/email/       EmailProvider abstraction (console/SMTP + factory)
    integrations/
      claude/               ClaudeProvider abstraction (Anthropic API + factory
                            + utils.complete() shared stream-to-string helper)
      obsidian/              ObsidianProvider abstraction (LocalVaultProvider,
                            markdown tag/link parsing, path-safety + factory)
      storage/               StorageProvider abstraction (LocalStorageProvider,
                            category+owner-namespaced, path-safety + factory)
    agents/                per-mode system prompts + orchestrator (chat turn:
                          persist -> build context (project + vault search for
                          Knowledge/Research modes) -> stream -> persist -> log)
    knowledge/             vault_analysis.py (deterministic duplicate/outdated/
                          broken-link/orphan detection, health score, graph
                          builder), gap_analysis.py (Claude-backed gap analysis,
                          same never-lose-input contract as agents/)
    documents/              generator.py (Claude-drafted content -> render ->
                          StorageProvider, same never-lose-input contract),
                          render.py (real markdown -> docx/pdf conversion)
    api/
      auth/               /api/auth/* routes
      users/              /api/users/* routes
      projects/            /api/projects/* routes
      history/              /api/history/* routes
      agent/                /api/agent/* routes (conversations, SSE chat, status)
      obsidian/              /api/obsidian/* routes (notes CRUD, search, status)
      knowledge/             /api/knowledge/* routes (health, graph, gap analyses)
      documents/              /api/documents/* routes (create/list/get/download/delete)
  alembic/                DB migrations
  tests/                  pytest suite (151 tests, real Postgres, no mocks)

frontend/
  index.html              session-aware redirect (dashboard vs login)
  pages/                  login, signup, forgot/reset password, verify-email,
                          dashboard, profile, settings, projects,
                          project-workspace, history, agent (AI Chat),
                          obsidian (vault browser), knowledge (Knowledge
                          Center), knowledge-gaps (Knowledge Gaps), documents
                          (Documents Studio)
  assets/
    css/                  design tokens (theme.css), auth layout, app shell,
                          workspace-layout.css (full-screen/split-screen),
                          agent.css (chat UI), obsidian.css (vault browser),
                          knowledge.css (health dashboard, SVG graph, gap results),
                          documents.css (draft form, format picker, file list)
    js/                   api client, theme, toast, nav/shell, generic confirm
                          modal, reusable split-screen/full-screen controller,
                          shared history-row renderer, SSE chat client,
                          minimal safe markdown preview renderer, force-directed
                          SVG knowledge graph renderer, page controllers
    vendor/                vendored Bootstrap 5 + Bootstrap Icons (no CDN
                          dependency — see below)
  components/             (reserved for shared HTML fragments as the app grows)

storage/
  obsidian_vaults/         default per-user vault root (see "Connecting a
                          real Obsidian vault" above)
  documents/{user_id}/…    real generated .md/.docx/.pdf files, written
                          through StorageProvider (Phase 7)
  images/videos/audio/…    generated-asset roots for future Image/Video/
                          Audio generation phases, same StorageProvider
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

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Postgres: either `docker compose up -d` from the repo root, or point
# DATABASE_URL at any local/remote Postgres instance.
cp .env.example .env   # edit DATABASE_URL / SECRET_KEY as needed

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/api/docs (disabled in production).

### Frontend

Static files — serve with any static server, e.g.:

```bash
cd frontend
python3 -m http.server 5173
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

151 tests covering signup, duplicate-email/weak-password/mismatch
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
cross-user ownership isolation, and `document` History logging) — all
against a real PostgreSQL test database and a real (temp-directory)
filesystem vault/storage root, no mocked ORM and no mocked filesystem.

There is deliberately no test that calls a real Anthropic API: this
deployment has no `ANTHROPIC_API_KEY` configured (see "Configuring a
real Claude connection" above), and the honest "not configured" path
is exactly what's under test.

## Roadmap

This repo follows the phased plan from the product spec:

1. ✅ **Foundation** — repo structure, backend/frontend skeleton, Postgres, env config
2. ✅ **Authentication** — signup/login/verify/reset/sessions/profile
3. ✅ **Core UI** — reusable full-screen/split-screen workspace shell, history, projects UI
4. ✅ **AI Agent** — Claude provider, orchestrator, chat, streaming, 7 modes (tool-calling architecture still to come)
5. ✅ **Obsidian** — per-user vault, search/read/create/update/append/move/delete, connection status, Knowledge/Research mode grounding (MCP/REST bridge to a live Obsidian.app instance is a possible future provider — the current one operates directly on vault files, which is what a live Obsidian instance is backed by anyway)
6. ✅ **Knowledge Intelligence** — gap/duplicate/outdated/broken-link/orphan detection, health score, knowledge graph, Claude-backed gap analysis, knowledge-update history, auto-update policy setting (Auto/Approval/Smart Auto — saved now, ready for the future automatic-apply capability)
7. 🟡 **Creative tools** — image/audio/video/document/design generation. **Document generation is done**: Claude-drafted content rendered to real Markdown/.docx/.pdf via `StorageProvider`, gated honestly by Claude configuration (see above). The new `StorageProvider` abstraction this introduced is what Image/Audio/Video generation will write through next. Image/Audio/Video/Website/3D Website/Poster/Logo/Graphic Design generation remain ⬜ — each needs its own real external generation API (OpenAI Images, Stability AI, ElevenLabs, etc.), architected the same way Claude is: a provider interface + factory, built and ready to configure, honestly "not configured" until real credentials are added.
8. ⬜ **Developer Studio** — website/3D website generation, live preview, deployment
9. ⬜ **Integration** — projects ↔ knowledge ↔ history ↔ files ↔ AI context ↔ activity log
10. ⬜ **Testing** — expanded integration/E2E/security test coverage
11. ⬜ **Final polish** — performance, accessibility, full responsive/theme QA

Each phase is expected to land as real, working, end-to-end functionality
— never a UI-only mockup — consistent with the project's "no placeholder
functionality" rule.
