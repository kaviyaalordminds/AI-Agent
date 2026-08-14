# AI Agent Platform

A full-stack AI Agent + Creative Studio + Obsidian Knowledge Intelligence
platform. This repository is being built in phases (see **Roadmap**
below); this README always reflects what's actually implemented, not the
full end-state vision.

## What's implemented (Phase 1 + 2: Foundation & Authentication)

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
- **No credit/usage-limit system** — by design, per the product spec.
- **Provider-abstraction pattern established**: `EmailProvider` (console
  for dev, SMTP for prod) is the first instance of the
  Claude/Obsidian/MCP/Storage/Deployment provider architecture the rest
  of the platform will follow — application code never talks to a vendor
  SDK or credential directly.

Everything above is fully wired end-to-end (frontend ↔ backend ↔
database) and covered by an automated test suite — nothing here is a
mockup or placeholder.

### What you'll see marked "planned for a later phase"

The sidebar, dashboard quick-create tiles, and Settings tabs for AI
Chat, Image/Video/Audio/Document/Website/Design studios, Projects,
Knowledge Center, Obsidian, History, and Deployments are visibly present
(matching the target navigation structure) but intentionally disabled —
clicking them shows an honest "planned for a later development phase"
message instead of a fake result. This is deliberate: the product spec
explicitly forbids fake success states, so until a module has a real
backend behind it, its UI says so rather than pretending.

## Architecture

```
backend/
  app/
    main.py            FastAPI app, CORS, error handlers, router mounting
    core/               settings (env-driven), logging
    database/            SQLAlchemy engine/session, declarative base
    models/              User, UserSession, UserSettings, EmailVerificationToken,
                          PasswordResetToken
    schemas/              Pydantic request/response models + validation
    security/             Argon2id hashing, token generation/hashing,
                          session + CSRF dependencies, rate limiting
    services/email/       EmailProvider abstraction (console/SMTP + factory)
    api/
      auth/               /api/auth/* routes
      users/              /api/users/* routes
  alembic/                DB migrations
  tests/                  pytest suite (30 tests, real Postgres, no mocks)

frontend/
  index.html              session-aware redirect (dashboard vs login)
  pages/                  login, signup, forgot/reset password, verify-email,
                          dashboard, profile, settings
  assets/
    css/                  design tokens (theme.css), auth layout, app shell
    js/                   api client, theme, toast, nav/shell, page controllers
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

30 tests covering signup, duplicate-email/weak-password/mismatch
rejection, email verification (incl. single-use/expiry), login (incl.
unverified-account block, wrong password, account lockout), logout,
logout-all, per-session revocation, forgot/reset password (incl.
single-use tokens and session revocation on reset), profile updates,
email change, password change, and settings persistence — all against a
real PostgreSQL test database, no mocked ORM.

## Roadmap

This repo follows the phased plan from the product spec:

1. ✅ **Foundation** — repo structure, backend/frontend skeleton, Postgres, env config
2. ✅ **Authentication** — signup/login/verify/reset/sessions/profile
3. ⬜ **Core UI** — full workspace shell (full-screen/split-screen panels), history, projects UI
4. ⬜ **AI Agent** — Claude provider, orchestrator, chat, streaming, tool architecture
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
