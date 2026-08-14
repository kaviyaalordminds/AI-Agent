import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.base import utcnow
from app.database.session import get_db
from app.models.token import EmailVerificationToken
from app.models.user import User
from app.models.user_settings import UserSettings
from app.schemas.auth import ChangePasswordRequest, MessageResponse, UserOut
from app.schemas.user import ChangeEmailRequest, SettingsOut, UpdateProfileRequest, UpdateSettingsRequest
from app.security.passwords import hash_password, verify_password
from app.security.sessions import get_current_user, require_csrf
from app.security.tokens import generate_token, hash_token
from app.services.email.factory import get_email_provider
from app.services.email.templates import verification_email

logger = logging.getLogger("api.users")
settings = get_settings()
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.avatar_url is not None:
        user.avatar_url = payload.avatar_url
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/me/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect."
        )
    user.password_hash = hash_password(payload.new_password)
    db.add(user)
    db.commit()
    return MessageResponse(message="Password changed successfully.")


@router.post("/me/change-email", response_model=MessageResponse)
def change_email(
    payload: ChangeEmailRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect."
        )

    new_email = payload.new_email.lower().strip()
    if new_email == user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This is already your current email address."
        )

    existing = db.query(User).filter(User.email == new_email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An account with this email address already exists."
        )

    user.email = new_email
    user.email_verified = False
    user.email_verified_at = None
    db.add(user)
    db.flush()

    raw_token = generate_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            email=new_email,
            expires_at=utcnow() + timedelta(hours=settings.email_verification_token_ttl_hours),
        )
    )
    db.commit()

    try:
        get_email_provider().send(verification_email(new_email, user.full_name, raw_token))
    except Exception:
        logger.exception("Failed to send verification email to %s", new_email)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Your email was updated, but the verification message could not be sent. "
                "Use 'Resend verification email' to try again."
            ),
        )

    return MessageResponse(
        message="Email updated. Please check your new inbox to verify this address."
    )


@router.get("/me/settings", response_model=SettingsOut)
def get_settings_endpoint(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    settings_row = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if settings_row is None:
        settings_row = UserSettings(user_id=user.id)
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return SettingsOut.model_validate(settings_row)


@router.patch("/me/settings", response_model=SettingsOut)
def update_settings_endpoint(
    payload: UpdateSettingsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings_row = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if settings_row is None:
        settings_row = UserSettings(user_id=user.id)

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(settings_row, field, value)

    db.add(settings_row)
    db.commit()
    db.refresh(settings_row)
    return SettingsOut.model_validate(settings_row)
