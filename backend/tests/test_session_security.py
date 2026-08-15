"""Session/cookie security coverage the Phase 10 audit found missing
entirely: no test inspected actual Set-Cookie attributes, exercised the
session_cookie_secure production-forcing validator, or used a session
past its natural expires_at (every existing "session revoked" test only
covers explicit revocation — logout/logout-all/password-reset)."""
from datetime import timedelta

from app.core.config import Settings
from app.database.base import utcnow
from app.models.session import UserSession
from app.models.user import User

_OWNER_EMAIL = "owner@example.com"
_OWNER_PASSWORD = "Str0ng!Passw0rd"


def _relogin_and_capture_set_cookie_headers(client):
    """auth_client's own login already happened before the test got the
    client, so its Set-Cookie response headers are gone by the time a
    test runs — re-login to capture them fresh. httpx's parsed
    `resp.cookies` jar doesn't expose attributes like HttpOnly/SameSite,
    only the raw `set-cookie` response headers do."""
    resp = client.post("/api/auth/login", json={"email": _OWNER_EMAIL, "password": _OWNER_PASSWORD})
    return resp.headers.get_list("set-cookie")


class TestSessionCookieAttributes:
    def test_session_cookie_is_httponly_and_samesite_lax(self, auth_client):
        client, _csrf = auth_client
        headers = _relogin_and_capture_set_cookie_headers(client)
        session_header = next(h for h in headers if h.startswith("aiagent_session="))
        assert "HttpOnly" in session_header
        assert "samesite=lax" in session_header.lower()
        assert "Path=/" in session_header

    def test_csrf_cookie_is_not_httponly_but_is_samesite_lax(self, auth_client):
        """Intentional: the frontend JS must be able to read this cookie
        to echo it back as X-CSRF-Token (double-submit pattern) — see
        app/security/sessions.py:set_session_cookies."""
        client, _csrf = auth_client
        headers = _relogin_and_capture_set_cookie_headers(client)
        csrf_header = next(h for h in headers if h.startswith("aiagent_csrf="))
        assert "HttpOnly" not in csrf_header
        assert "samesite=lax" in csrf_header.lower()

    def test_neither_cookie_is_secure_when_session_cookie_secure_is_false(self, auth_client):
        """This test suite runs with SESSION_COOKIE_SECURE=false
        (conftest.py) — confirms the flag actually controls the Secure
        attribute rather than it always being set or always absent."""
        client, _csrf = auth_client
        headers = _relogin_and_capture_set_cookie_headers(client)
        assert not any("; secure" in h.lower() for h in headers)


class TestSessionCookieSecureProductionValidator:
    def test_forced_true_in_production_even_if_configured_false(self):
        settings = Settings(app_env="production", session_cookie_secure=False)
        assert settings.session_cookie_secure is True

    def test_forced_true_in_staging_even_if_configured_false(self):
        settings = Settings(app_env="staging", session_cookie_secure=False)
        assert settings.session_cookie_secure is True

    def test_not_forced_in_development(self):
        settings = Settings(app_env="development", session_cookie_secure=False)
        assert settings.session_cookie_secure is False

    def test_explicit_true_in_production_stays_true(self):
        settings = Settings(app_env="production", session_cookie_secure=True)
        assert settings.session_cookie_secure is True


def _expire_owners_session(db_session):
    user = db_session.query(User).filter(User.email == _OWNER_EMAIL).first()
    session_row = (
        db_session.query(UserSession)
        .filter(UserSession.user_id == user.id)
        .order_by(UserSession.created_at.desc())
        .first()
    )
    session_row.expires_at = utcnow() - timedelta(hours=1)
    db_session.add(session_row)
    db_session.commit()


class TestSessionExpiry:
    def test_naturally_expired_session_is_rejected(self, auth_client, db_session):
        """Every existing 'session revoked' test only covers explicit
        revocation (logout/logout-all/password-reset) — this is the one
        genuinely missing case: a session past its own expires_at, which
        _get_session_from_cookie (app/security/sessions.py) checks via a
        plain datetime comparison, never previously exercised."""
        client, _csrf = auth_client
        _expire_owners_session(db_session)

        resp = client.get("/api/users/me")
        assert resp.status_code == 401

    def test_expired_session_also_rejected_on_state_changing_endpoint(self, auth_client, db_session):
        """Confirms this isn't just a GET-path check — require_csrf also
        depends on get_current_session, so a state-changing request with
        an expired session must be rejected the same way."""
        client, csrf = auth_client
        _expire_owners_session(db_session)

        resp = client.patch("/api/users/me", json={"full_name": "New Name"}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 401


class TestRevokedSessionOnStateChangingEndpoint:
    def test_logged_out_session_rejected_on_state_changing_endpoint(self, auth_client):
        """test_auth.py's existing logout test only checks a GET
        (/api/users/me) afterward — this confirms a POST/PATCH also
        correctly fails with a revoked session, not just reads."""
        client, csrf = auth_client
        logout_resp = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        assert logout_resp.status_code == 200

        resp = client.patch("/api/users/me", json={"full_name": "New Name"}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 401
