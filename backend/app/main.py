import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders

import app.models  # noqa: F401  (registers all ORM models before first use)
from app.api.agent.router import router as agent_router
from app.api.auth.router import router as auth_router
from app.api.deployments.router import router as deployments_router
from app.api.documents.router import router as documents_router
from app.api.generation.router import router as generation_router
from app.api.history.router import router as history_router
from app.api.jobs.router import router as jobs_router
from app.api.knowledge.router import router as knowledge_router
from app.api.obsidian.router import router as obsidian_router
from app.api.projects.router import router as projects_router
from app.api.system.router import router as system_router
from app.api.users.router import router as users_router
from app.api.websites.router import router as websites_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.integrations.storage.errors import FileTooLargeError, InvalidStoragePathError

settings = get_settings()
configure_logging()
logger = logging.getLogger("app")

app = FastAPI(
    title=settings.app_name,
    description="Shadow AI — Creative Studio + Obsidian Knowledge Intelligence Platform API",
    version="0.1.0",
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
)

class SecurityHeadersMiddleware:
    """Sets X-Content-Type-Options: nosniff on every response.

    Deliberately a raw ASGI middleware, NOT @app.middleware("http")/
    BaseHTTPMiddleware. BaseHTTPMiddleware wraps every response body
    through an internal byte-piping/backpressure mechanism (to let the
    dispatch function inspect and return a *new* response object), which
    adds real per-request latency and is a well-documented source of
    slowdowns and hangs on slower or streaming responses (AI Chat's SSE
    stream in particular) — a request that used to finish just under the
    frontend's 20s AbortController timeout (see api.js) can tip over it
    once wrapped, surfacing as a spurious "server took too long" error
    with no actual backend hang. A pure ASGI middleware that only touches
    the response-start message's headers (as below) has none of that
    overhead — this is the same pattern CORSMiddleware already uses,
    which is why adding CORS never caused this class of problem."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("X-Content-Type-Options", "nosniff")
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.resolved_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Without max_age, browsers re-run the OPTIONS preflight on every
    # single unsafe request (POST/PATCH/DELETE) rather than caching it —
    # doubling the round trips for every state-changing call, including
    # login. Caching it for 10 minutes is a safe, standard optimization
    # with no security implication (it only caches which methods/headers
    # are allowed, not any actual response data).
    max_age=600,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"] if p != "body")
        errors.append({"field": loc, "message": err["msg"]})
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation failed.", "errors": errors},
    )


@app.exception_handler(FileTooLargeError)
async def file_too_large_handler(request: Request, exc: FileTooLargeError):
    """A few endpoints (video reference images, AI-drafted/structured
    document rendering) write caller-influenced data through
    StorageProvider synchronously in the request path, outside the job
    queue's own StorageError handling (see app/jobs/worker.py) — without
    this, an over-the-limit write raised FileTooLargeError, which fell
    through to the generic 500 handler below instead of a clean 4xx."""
    return JSONResponse(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        content={"detail": str(exc)},
    )


@app.exception_handler(InvalidStoragePathError)
async def invalid_storage_path_handler(request: Request, exc: InvalidStoragePathError):
    logger.warning("Invalid storage path: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Invalid file reference."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    response = JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred."},
    )
    # Starlette wires a handler registered for the bare `Exception` class
    # to ServerErrorMiddleware, not ExceptionMiddleware — and
    # ServerErrorMiddleware sits OUTSIDE CORSMiddleware in the ASGI stack
    # (see Starlette's Starlette.build_middleware_stack: `if key in (500,
    # Exception): error_handler = value`, which becomes
    # ServerErrorMiddleware's handler, added before self.user_middleware).
    # That means this response's Access-Control-* headers are never added
    # by CORSMiddleware, and the browser reports every single backend
    # exception as a CORS failure ("No 'Access-Control-Allow-Origin'
    # header is present") no matter what actually went wrong — reproduced
    # and confirmed directly against this handler, not assumed. Add the
    # header ourselves, mirroring the exact allow-list CORSMiddleware
    # itself uses (settings.frontend_url) so this never reflects an
    # arbitrary Origin back to the caller.
    origin = request.headers.get("origin")
    if origin in settings.resolved_cors_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


@app.on_event("startup")
def _apply_pending_migrations() -> None:
    """Auto-apply any pending Alembic migrations on process startup.

    Root cause of a real recurring bug class (reproduced directly: with
    the `error_type` column absent, GET /api/jobs?type=image/video
    failed with sqlalchemy.exc.ProgrammingError: UndefinedColumn, which
    the generic exception handler above turns into a 500 the browser
    shows as "An unexpected server error occurred" — see the git history
    around migration 3bac8ec7a505 for the earlier incident this exact
    failure mode caused): a developer pulls new code that adds a column/
    table but forgets to separately run `alembic upgrade head` before
    restarting the server, so the ORM model and the actual database
    schema disagree. Every migration in alembic/versions/ is additive
    (add_column/create_table, no destructive drops in upgrade()), so
    running this on every startup is safe and, per Alembic's own
    design, a no-op when the database is already at head.

    Skipped entirely in the test environment: tests build their schema
    directly via Base.metadata.create_all() (see tests/conftest.py),
    which has no `alembic_version` bookkeeping table, so running Alembic
    against it would fail with "relation already exists" — and
    TestClient's `with` context re-triggers this startup event on every
    single test.

    Failure here is logged loudly but never crashes the process: an
    unreachable database will fail obviously on the very first real
    request anyway (see GET /api/system/providers/health), and refusing
    to serve ANY request — including ones that don't touch the
    database at all — over a migration-specific failure would be a
    worse outcome than the bug this fixes.
    """
    if settings.app_env == "testing":
        return
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    try:
        alembic_ini = Path(__file__).resolve().parent.parent / "alembic.ini"
        cfg = Config(str(alembic_ini))
        cfg.set_main_option("script_location", str(alembic_ini.parent / "alembic"))
        command.upgrade(cfg, "head")
        logger.info("Database schema is up to date (alembic upgrade head).")
    except Exception:
        logger.exception(
            "Could not auto-apply database migrations at startup. The app will keep "
            "starting, but any endpoint touching an out-of-date table may fail until "
            "this is resolved — run `alembic upgrade head` manually from backend/."
        )
    finally:
        # alembic/env.py calls logging.config.fileConfig(alembic.ini) as a
        # side effect of the command above. fileConfig()'s default
        # disable_existing_loggers=True does something easy to miss:
        # it doesn't just replace the root logger's handlers, it sets
        # `.disabled = True` directly on every Logger object that
        # already existed (app, uvicorn, api.auth, etc.) — reproduced
        # directly: resetting root.handlers alone left every one of
        # those loggers silently dropping all future messages, so
        # nothing (not even uvicorn's own "Application startup
        # complete.") logged again for the rest of the process. Clear
        # that flag on every logger, then reapply this app's own
        # configure_logging() so nothing downstream of this hook is
        # silently unlogged.
        for existing_logger in logging.root.manager.loggerDict.values():
            if isinstance(existing_logger, logging.Logger):
                existing_logger.disabled = False
        configure_logging()


@app.on_event("startup")
def _validate_obsidian_vault_path() -> None:
    """OBSIDIAN_VAULT_PATH (see app/core/config.py, app/integrations/
    obsidian/factory.py) is optional — most deployments leave it unset
    and get the default per-user vault layout, which needs no validation
    here. When it IS set (a single-user deployment pointed at a real
    existing vault), report clearly at startup whether that directory is
    actually reachable, without crashing the rest of the app if it
    isn't: Obsidian being unavailable must never take down chat,
    documents, or any other unrelated feature."""
    if not settings.obsidian_vault_path:
        return
    from pathlib import Path

    path = Path(settings.obsidian_vault_path)
    if path.exists() and path.is_dir():
        logger.info("OBSIDIAN_VAULT_PATH is configured and reachable: %s", path)
    elif path.exists():
        logger.warning("OBSIDIAN_VAULT_PATH exists but is not a directory: %s", path)
    else:
        logger.warning(
            "OBSIDIAN_VAULT_PATH is configured but does not exist yet: %s — it will be "
            "auto-provisioned (folder structure + welcome note) on first Obsidian request.",
            path,
        )


app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(users_router, prefix=settings.api_prefix)
app.include_router(projects_router, prefix=settings.api_prefix)
app.include_router(history_router, prefix=settings.api_prefix)
app.include_router(agent_router, prefix=settings.api_prefix)
app.include_router(obsidian_router, prefix=settings.api_prefix)
app.include_router(knowledge_router, prefix=settings.api_prefix)
app.include_router(documents_router, prefix=settings.api_prefix)
app.include_router(jobs_router, prefix=settings.api_prefix)
app.include_router(generation_router, prefix=settings.api_prefix)
app.include_router(system_router, prefix=settings.api_prefix)
app.include_router(websites_router, prefix=settings.api_prefix)
app.include_router(deployments_router, prefix=settings.api_prefix)


@app.get(f"{settings.api_prefix}/health")
def health_check():
    return {"status": "ok", "environment": settings.app_env}


@app.get("/health")
def bare_health_check():
    """Unprefixed liveness endpoint for load balancers/orchestrators that
    probe a fixed /health path — deliberately trivial (no DB/provider
    calls) so it reflects only "is the process up", not deeper provider
    status (see /api/system/providers/health for that)."""
    return {"status": "ok"}
