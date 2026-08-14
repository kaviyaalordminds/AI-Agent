from datetime import timedelta

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.base import utcnow
from app.database.session import get_db
from app.models.session import UserSession
from app.models.user import User
from app.security.tokens import constant_time_compare, generate_token, hash_token

settings = get_settings()


def create_session(db: Session, user: User, request: Request) -> tuple[UserSession, str]:
    raw_token = generate_token()
    csrf_token = generate_token(16)
    now = utcnow()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        csrf_token=csrf_token,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        last_active_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, raw_token


def set_session_cookies(response: Response, session: UserSession, raw_token: str) -> None:
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    # CSRF cookie is intentionally NOT httponly: the frontend JS reads it and
    # echoes it back as the X-CSRF-Token header (double-submit pattern).
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=session.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


def _get_session_from_cookie(
    db: Session, raw_token: str | None
) -> UserSession | None:
    if not raw_token:
        return None
    token_hash = hash_token(raw_token)
    session = db.query(UserSession).filter(UserSession.token_hash == token_hash).first()
    if session is None:
        return None
    if session.revoked_at is not None:
        return None
    if session.expires_at.replace(tzinfo=None) < utcnow().replace(tzinfo=None):
        return None
    return session


def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
) -> UserSession:
    raw_token = request.cookies.get(settings.session_cookie_name)
    session = _get_session_from_cookie(db, raw_token)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    session.last_active_at = utcnow()
    db.add(session)
    db.commit()
    return session


def get_current_user(
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> User:
    user = db.query(User).filter(User.id == session.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    return user


def get_optional_user(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    raw_token = request.cookies.get(settings.session_cookie_name)
    session = _get_session_from_cookie(db, raw_token)
    if session is None:
        return None
    return db.query(User).filter(User.id == session.user_id).first()


def require_csrf(
    request: Request,
    session: UserSession = Depends(get_current_session),
) -> None:
    """Double-submit CSRF check for authenticated state-changing requests."""
    header_token = request.headers.get("x-csrf-token")
    if not header_token or not constant_time_compare(header_token, session.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or missing CSRF token."
        )
