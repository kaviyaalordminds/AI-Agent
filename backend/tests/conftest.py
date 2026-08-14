import os

os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_URL"] = "postgresql+psycopg://ai_agent:ai_agent@localhost:5432/ai_agent_test"
os.environ["EMAIL_PROVIDER"] = "console"
os.environ["SESSION_COOKIE_SECURE"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.database.base import Base
from app.database.session import get_db
from app.main import app as fastapi_app
from app.security import rate_limit

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(TEST_DATABASE_URL, future=True)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(autouse=True)
def _clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
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
