import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

_PASSWORD_MIN_LEN = 10


def validate_password_strength(password: str) -> str:
    if len(password) < _PASSWORD_MIN_LEN:
        raise ValueError(f"Password must be at least {_PASSWORD_MIN_LEN} characters long.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number.")
    if not re.search(r"[^\w\s]", password):
        raise ValueError("Password must contain at least one special character.")
    return password


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str
    confirm_password: str
    accept_terms: bool

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Full name is required.")
        return v

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("accept_terms")
    @classmethod
    def _must_accept_terms(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must accept the Terms of Service to create an account.")
        return v

    @field_validator("confirm_password")
    @classmethod
    def _passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("confirm_password")
    @classmethod
    def _passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match.")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("confirm_password")
    @classmethod
    def _passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match.")
        return v


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str


class UserOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    email_verified: bool
    avatar_url: str | None
    created_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    id: uuid.UUID
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    last_active_at: datetime
    expires_at: datetime
    is_current: bool = False

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str
