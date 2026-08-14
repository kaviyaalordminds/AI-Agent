# AI Agent Platform

A full-stack AI Agent + Creative Studio + Obsidian Knowledge Intelligence
platform. This repository is being built in phases (see **Roadmap**
below); this README always reflects what's actually implemented, not the
full end-state vision.

## What's implemented (Phase 1–4: Foundation, Authentication, Core UI & AI Agent)

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
- **No credit/usage-limit system** — by design, per the product spec.
- **Provider-abstraction pattern**: `EmailProvider` and `ClaudeProvider`
  establish the pattern the remaining Obsidian/MCP/Storage/Deployment
  integrations will follow — application code never talks to a vendor
  SDK or credential directly.

Everything above is fully wired end-to-end (frontend ↔ backend ↔
database ↔ Claude API) and covered by an automated test suite — nothing
here is a mockup or placeholder.

### What you'll see marked "planned for a later phase"

The sidebar, dashboard quick-create tiles, and Settings tabs for
Image/Video/Audio/Document/Website/Design studios, Knowledge Center,
Obsidian, and Deployments are visibly present (matching the target
navigation structure) but intentionally disabled — clicking them shows
an honest "planned for a later development phase" message instead of a
fake result. Within AI Chat and the project workspace's Chat tab, each
mode's system prompt is explicit about which of its described
capabilities (Obsidian search, generation tools, code execution,
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
status immediately.

## Architecture

```
backend/
  app/
    main.py            FastAPI app, CORS, error handlers, router mounting
    core/               settings (env-driven), logging
    database/            SQLAlchemy engine/session, declarative base
    models/              User, UserSession, UserSettings, EmailVerificationToken,
                          PasswordResetToken, Project, HistoryEntry,
                          Conversation, Message
    schemas/              Pydantic request/response models + validation
    security/             Argon2id hashing, token generation/hashing,
                          session + CSRF dependencies, rate limiting
    services/email/       EmailProvider abstraction (console/SMTP + factory)
    integrations/claude/   ClaudeProvider abstraction (Anthropic API + factory)
    agents/                per-mode system prompts + orchestrator (chat turn:
                          persist -> build context -> stream -> persist -> log)
    api/
      auth/               /api/auth/* routes
      users/              /api/users/* routes
      projects/            /api/projects/* routes
      history/              /api/history/* routes
      agent/                /api/agent/* routes (conversations, SSE chat, status)
  alembic/                DB migrations
  tests/                  pytest suite (75 tests, real Postgres, no mocks)

frontend/
  index.html              session-aware redirect (dashboard vs login)
  pages/                  login, signup, forgot/reset password, verify-email,
                          dashboard, profile, settings, projects,
                          project-workspace, history, agent (AI Chat)
  assets/
    css/                  design tokens (theme.css), auth layout, app shell,
                          workspace-layout.css (full-screen/split-screen),
                          agent.css (chat UI)
    js/                   api client, theme, toast, nav/shell, generic confirm
                          modal, reusable split-screen/full-screen controller,
                          shared history-row renderer, SSE chat client, page
                          controllers
    vendor/                vendored Bootstrap 5 + Bootstrap Icons (no CDN
                          dependency — see below)
  components/             (reserved for shared HTML fragments as the app grows)

storage/                  generated-asset root for the future StorageProvider
                          (images/videos/audio/documents/websites/projects)
docker-compose.yml        local PostgreSQL for development
```

**Why vendored Bootstrap instead of a CDN `<link>`?** Some network
environments (including the one this was built in) block CDN hosts like
`cdn.jsdelivr.net` outright. A production app that hard-depends on a
third-party CDN for its CSS framework is one blocked request away from
rendering unstyled. Bootstrap 5.3.3 and Bootstrap Icons 1.11.3 are
vendored under `frontend/assets/vendor/` (~700KB) instead.

### Hybrid storage model (per spec)

- **PostgreSQL** — users, sessions, tokens, and (in later phases)
  projects, chat history, generation history, job status, file
  *metadata*, deployment metadata.
- **Filesystem (`storage/`)** — the actual generated binary assets.
  Postgres stores a reference, never the blob.
- **Obsidian** (later phase) — the knowledge layer: notes, research,
  project documentation, AI memory. Never used as a database substitute.

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

75 tests covering signup, duplicate-email/weak-password/mismatch
rejection, email verification (incl. single-use/expiry), login (incl.
unverified-account block, wrong password, account lockout), logout,
logout-all, per-session revocation, forgot/reset password (incl.
single-use tokens and session revocation on reset), profile updates,
email change, password change, settings persistence, project CRUD
(create/rename/archive/unarchive/duplicate/delete), cross-user project
ownership isolation, history listing/filtering/pagination/rename/
move/delete, and the AI Agent module (conversation CRUD, cross-user
isolation, streamed chat against a fake deterministic provider,
project-context injection into the system prompt, history logging on
both success and failure, and — the one that mattered most — a
regression test proving a user's message is persisted even when Claude
isn't configured) — all against a real PostgreSQL test database, no
mocked ORM.

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
5. ⬜ **Obsidian** — MCP integration, vault search/read/create/update, connection management
6. ⬜ **Knowledge Intelligence** — gap/duplicate/outdated detection, knowledge graph, auto-update policies
7. ⬜ **Creative tools** — image/audio/video/document/design generation
8. ⬜ **Developer Studio** — website/3D website generation, live preview, deployment
9. ⬜ **Integration** — projects ↔ knowledge ↔ history ↔ files ↔ AI context ↔ activity log
10. ⬜ **Testing** — expanded integration/E2E/security test coverage
11. ⬜ **Final polish** — performance, accessibility, full responsive/theme QA

Each phase is expected to land as real, working, end-to-end functionality
— never a UI-only mockup — consistent with the project's "no placeholder
functionality" rule.
