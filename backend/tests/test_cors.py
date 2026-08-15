"""Regression coverage for a real bug: any unhandled backend exception
made the browser report a CORS failure ("No 'Access-Control-Allow-Origin'
header is present"), even against a request with a perfectly valid,
allow-listed Origin. Root cause: Starlette routes a handler registered
for the bare `Exception` class to ServerErrorMiddleware, which sits
OUTSIDE CORSMiddleware in the ASGI stack — so responses from that handler
never picked up CORS headers. Also covers resolved_cors_origins, which
lets the app be opened at either localhost or 127.0.0.1 in local dev
without breaking SameSite=Lax session cookies.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.database.session import get_db
from app.main import app as fastapi_app


@pytest.fixture
def non_raising_client():
    """ServerErrorMiddleware sends the actual HTTP response to the real
    client normally, then re-raises the original exception afterward
    purely so a wrapping test harness can see the traceback — the
    default TestClient(raise_server_exceptions=True) deliberately
    surfaces that re-raise as a Python exception in the test process,
    which is right for catching genuinely-unexpected errors elsewhere in
    the suite, but wrong here since these tests intentionally trigger a
    failure and need to inspect the resulting HTTP response instead."""
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        yield c


class TestResolvedCorsOrigins:
    def test_localhost_frontend_url_trusts_both_local_hostnames(self):
        settings = Settings(frontend_url="http://localhost:5173")
        assert set(settings.resolved_cors_origins) == {
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        }

    def test_127_frontend_url_also_trusts_both_local_hostnames(self):
        """Whichever of the two local hostnames FRONTEND_URL is set to,
        both are trusted the same way — the point is neither hostname is
        left out, not that one is canonical."""
        settings = Settings(frontend_url="http://127.0.0.1:5173")
        assert set(settings.resolved_cors_origins) == {
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        }

    def test_non_local_frontend_url_is_trusted_as_the_single_exact_origin(self):
        """A real deployment host must never get the localhost/127.0.0.1
        dual-trust treatment — only the exact configured origin."""
        settings = Settings(frontend_url="https://app.example.com")
        assert settings.resolved_cors_origins == ["https://app.example.com"]


class TestUnhandledExceptionKeepsCorsHeaders:
    def test_500_response_still_carries_cors_headers_for_allowed_origin(self, non_raising_client, monkeypatch):
        def _broken_get_db():
            raise RuntimeError("simulated unexpected failure")
            yield  # pragma: no cover — never reached, required for FastAPI to treat this as a generator dependency

        fastapi_app.dependency_overrides[get_db] = _broken_get_db
        try:
            resp = non_raising_client.post(
                "/api/auth/login",
                json={"email": "someone@example.com", "password": "whatever123"},
                headers={"Origin": "http://localhost:5173"},
            )
        finally:
            from tests.conftest import _override_get_db

            fastapi_app.dependency_overrides[get_db] = _override_get_db

        assert resp.status_code == 500
        assert resp.json() == {"detail": "An unexpected server error occurred."}
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_500_response_omits_cors_headers_for_disallowed_origin(self, non_raising_client, monkeypatch):
        """Never reflect an arbitrary Origin back — only the ones
        resolved_cors_origins actually trusts."""

        def _broken_get_db():
            raise RuntimeError("simulated unexpected failure")
            yield  # pragma: no cover

        fastapi_app.dependency_overrides[get_db] = _broken_get_db
        try:
            resp = non_raising_client.post(
                "/api/auth/login",
                json={"email": "someone@example.com", "password": "whatever123"},
                headers={"Origin": "https://evil.example.com"},
            )
        finally:
            from tests.conftest import _override_get_db

            fastapi_app.dependency_overrides[get_db] = _override_get_db

        assert resp.status_code == 500
        assert "access-control-allow-origin" not in resp.headers

    def test_500_response_carries_cors_headers_for_127_variant_too(self, non_raising_client, monkeypatch):
        def _broken_get_db():
            raise RuntimeError("simulated unexpected failure")
            yield  # pragma: no cover

        fastapi_app.dependency_overrides[get_db] = _broken_get_db
        try:
            resp = non_raising_client.post(
                "/api/auth/login",
                json={"email": "someone@example.com", "password": "whatever123"},
                headers={"Origin": "http://127.0.0.1:5173"},
            )
        finally:
            from tests.conftest import _override_get_db

            fastapi_app.dependency_overrides[get_db] = _override_get_db

        assert resp.status_code == 500
        assert resp.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
