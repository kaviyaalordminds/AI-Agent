import logging
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.base import utcnow
from app.database.session import get_db
from app.models.session import UserSession
from app.models.token import EmailVerificationToken, PasswordResetToken
from app.models.user import User
from app.models.user_settings import UserSettings
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SessionOut,
    SignupRequest,
    UserOut,
    VerifyEmailRequest,
)
from app.security.passwords import hash_password, verify_password
from app.security.rate_limit import enforce_rate_limit
from app.security.sessions import (
    clear_session_cookies,
    create_session,
    get_current_session,
    get_current_user,
    require_csrf,
    set_session_cookies,
)
from app.security.tokens import generate_token, hash_token
from app.services.email.factory import get_email_provider
from app.services.email.templates import password_reset_email, verification_email

logger = logging.getLogger("api.auth")
settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])

# Generic messages that do not reveal whether an email exists in the system.
_GENERIC_RESET_MESSAGE = (
    "If an account exists for that email address, a password reset link has been sent."
)
_GENERIC_VERIFICATION_MESSAGE = (
    "If an account exists for that email address, a verification link has been sent."
)


def _issue_verification_token(db: Session, user: User) -> str:
    raw_token = generate_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            email=user.email,
            expires_at=utcnow() + timedelta(hours=settings.email_verification_token_ttl_hours),
        )
    )
    db.commit()
    return raw_token


@router.post("/signup", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, bucket="signup", max_requests=5)

    email = payload.email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    user = User(
        full_name=payload.full_name,
        email=email,
        password_hash=hash_password(payload.password),
        email_verified=False,
    )
    db.add(user)
    db.flush()
    db.add(UserSettings(user_id=user.id))
    db.commit()
    db.refresh(user)

    raw_token = _issue_verification_token(db, user)
    try:
        get_email_provider().send(verification_email(user.email, user.full_name, raw_token))
    except Exception:
        logger.exception("Failed to send verification email to %s", user.email)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Your account was created, but the verification email could not be sent. "
                "Use 'Resend verification email' to try again."
            ),
        )

    return MessageResponse(
        message="Account created. Please check your email to verify your account before logging in."
    )


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(payload.token)
    record = (
        db.query(EmailVerificationToken)
        .filter(EmailVerificationToken.token_hash == token_hash)
        .first()
    )
    if record is None or record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has already been used.",
        )
    if record.expires_at.replace(tzinfo=None) < utcnow().replace(tzinfo=None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link has expired. Please request a new one.",
        )

    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification link.")

    user.email_verified = True
    user.email_verified_at = utcnow()
    record.used_at = utcnow()
    db.add_all([user, record])
    db.commit()

    return MessageResponse(message="Your email has been verified. You can now log in.")


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    payload: ResendVerificationRequest, request: Request, db: Session = Depends(get_db)
):
    enforce_rate_limit(request, bucket="resend-verification", max_requests=3)

    email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if user is not None and not user.email_verified:
        raw_token = _issue_verification_token(db, user)
        try:
            get_email_provider().send(verification_email(user.email, user.full_name, raw_token))
        except Exception:
            logger.exception("Failed to resend verification email to %s", user.email)

    return MessageResponse(message=_GENERIC_VERIFICATION_MESSAGE)


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce_rate_limit(request, bucket="login", max_requests=10)

    email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()

    generic_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password."
    )

    if user is None:
        raise generic_error

    if user.locked_until is not None and user.locked_until.replace(tzinfo=None) > utcnow().replace(
        tzinfo=None
    ):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                f"Too many failed login attempts. Try again after "
                f"{user.locked_until.strftime('%H:%M UTC')}."
            ),
        )

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.login_max_attempts:
            user.locked_until = utcnow() + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_login_attempts = 0
        db.add(user)
        db.commit()
        raise generic_error

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before logging in.",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is disabled.")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    db.add(user)
    db.commit()

    session, raw_token = create_session(db, user, request)
    set_session_cookies(response, session, raw_token)

    return UserOut.model_validate(user)


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    session.revoked_at = utcnow()
    db.add(session)
    db.commit()
    clear_session_cookies(response)
    return MessageResponse(message="Logged out.")


@router.post("/logout-all", response_model=MessageResponse)
def logout_all(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    db.query(UserSession).filter(
        UserSession.user_id == user.id, UserSession.revoked_at.is_(None)
    ).update({UserSession.revoked_at: utcnow()})
    db.commit()
    clear_session_cookies(response)
    return MessageResponse(message="Logged out from all devices.")


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    request: Request,
    current_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    current_raw_token = request.cookies.get(settings.session_cookie_name)
    sessions = (
        db.query(UserSession)
        .filter(UserSession.user_id == current_session.user_id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_active_at.desc())
        .all()
    )
    out = []
    for s in sessions:
        item = SessionOut.model_validate(s)
        item.is_current = s.id == current_session.id
        out.append(item)
    return out


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
def revoke_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    target = (
        db.query(UserSession)
        .filter(UserSession.id == session_id, UserSession.user_id == user.id)
        .first()
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    target.revoked_at = utcnow()
    db.add(target)
    db.commit()
    return MessageResponse(message="Session revoked.")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)
):
    enforce_rate_limit(request, bucket="forgot-password", max_requests=5)

    email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if user is not None:
        raw_token = generate_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                expires_at=utcnow()
                + timedelta(minutes=settings.password_reset_token_ttl_minutes),
            )
        )
        db.commit()
        try:
            get_email_provider().send(password_reset_email(user.email, user.full_name, raw_token))
        except Exception:
            logger.exception("Failed to send password reset email to %s", user.email)

    return MessageResponse(message=_GENERIC_RESET_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(payload.token)
    record = (
        db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()
    )
    if record is None or record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link is invalid or has already been used.",
        )
    if record.expires_at.replace(tzinfo=None) < utcnow().replace(tzinfo=None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link has expired. Please request a new one.",
        )

    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset link.")

    user.password_hash = hash_password(payload.new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    record.used_at = utcnow()

    # Resetting a password revokes every existing session, in case the
    # original credentials were compromised.
    db.query(UserSession).filter(
        UserSession.user_id == user.id, UserSession.revoked_at.is_(None)
    ).update({UserSession.revoked_at: utcnow()})

    db.add_all([user, record])
    db.commit()

    return MessageResponse(message="Your password has been reset. You can now log in.")
