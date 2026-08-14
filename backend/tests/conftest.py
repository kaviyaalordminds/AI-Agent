import os

os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_URL"] = "postgresql+psycopg://ai_agent:ai_agent@localhost:5432/ai_agent_test"
os.environ["EMAIL_PROVIDER"] = "console"
os.environ["SESSION_COOKIE_SECURE"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database.session as app_db_session
import app.models  # noqa: F401
from app.database.base import Base
from app.database.session import get_db
from app.main import app as fastapi_app
from app.security import rate_limit

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(TEST_DATABASE_URL, future=True)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(autouse=True)
def _obsidian_vault_tmp(tmp_path):
    """Each test gets its own throwaway vault root (pytest cleans up
    tmp_path automatically), so vault tests never touch the real
    storage/obsidian_vaults directory or leak state between tests."""
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.obsidian_vault_root
    settings.obsidian_vault_root = str(tmp_path / "obsidian_vaults")
    yield
    settings.obsidian_vault_root = original


@pytest.fixture(autouse=True)
def _storage_root_tmp(tmp_path):
    """Each test gets its own throwaway storage root, so generated-asset
    tests never touch the real storage/ directory or leak state between
    tests (same isolation strategy as _obsidian_vault_tmp above)."""
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.storage_root
    settings.storage_root = str(tmp_path / "storage")
    yield
    settings.storage_root = original


@pytest.fixture(autouse=True)
def _clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # app.database.session.engine is a *separate* connection pool from the
    # one above (production code — e.g. the agent chat SSE stream — opens
    # its own session lazily rather than via the get_db override). Its
    # pooled connections cache Postgres type OIDs (for our enum columns)
    # that go stale the moment the tables above are dropped and recreated,
    # producing "cache lookup failed for type N" errors. Disposing it forces
    # fresh connections with a fresh type cache on next use.
    app_db_session.engine.dispose()
    rate_limit._buckets.clear()
    yield
    Base.metadata.drop_all(bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


fastapi_app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture
def client():
    with TestClient(fastapi_app) as c:
        yield c


@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_client(client, email_outbox):
    """A TestClient already signed up, verified, and logged in as a fresh
    user. Returns (client, csrf_token) — pass csrf_token as the
    X-CSRF-Token header on any state-changing request."""
    import re

    email = "owner@example.com"
    password = "Str0ng!Passw0rd"
    client.post(
        "/api/auth/signup",
        json={
            "full_name": "Project Owner",
            "email": email,
            "password": password,
            "confirm_password": password,
            "accept_terms": True,
        },
    )
    token = re.search(r"token=([A-Za-z0-9_\-]+)", email_outbox[-1].text_body).group(1)
    client.post("/api/auth/verify-email", json={"token": token})
    login_resp = client.post("/api/auth/login", json={"email": email, "password": password})
    csrf = login_resp.cookies["aiagent_csrf"]
    return client, csrf


@pytest.fixture
def email_outbox(monkeypatch):
    """Captures every EmailMessage the app attempts to send, instead of
    hitting the real console/SMTP provider, so tests can pull verification
    and password-reset tokens out of the rendered email body."""
    import app.api.auth.router as auth_router_module
    import app.api.users.router as users_router_module

    outbox: list = []

    class _FakeProvider:
        def send(self, message):
            outbox.append(message)

    fake = _FakeProvider()
    monkeypatch.setattr(auth_router_module, "get_email_provider", lambda: fake)
    monkeypatch.setattr(users_router_module, "get_email_provider", lambda: fake)
    return outbox
