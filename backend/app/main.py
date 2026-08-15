import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import app.models  # noqa: F401  (registers all ORM models before first use)
from app.api.agent.router import router as agent_router
from app.api.auth.router import router as auth_router
from app.api.documents.router import router as documents_router
from app.api.generation.router import router as generation_router
from app.api.history.router import router as history_router
from app.api.jobs.router import router as jobs_router
from app.api.knowledge.router import router as knowledge_router
from app.api.obsidian.router import router as obsidian_router
from app.api.projects.router import router as projects_router
from app.api.system.router import router as system_router
from app.api.users.router import router as users_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging()
logger = logging.getLogger("app")

app = FastAPI(
    title=settings.app_name,
    description="AI Agent + Creative Studio + Obsidian Knowledge Intelligence Platform API",
    version="0.1.0",
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
)

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
