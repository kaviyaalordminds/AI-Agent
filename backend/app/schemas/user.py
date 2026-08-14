from pydantic import BaseModel, EmailStr, Field


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    avatar_url: str | None = None


class ChangeEmailRequest(BaseModel):
    new_email: EmailStr
    current_password: str


class UpdateSettingsRequest(BaseModel):
    theme: str | None = Field(default=None, pattern="^(light|dark)$")
    language: str | None = None
    sidebar_collapsed: bool | None = None
    ai_settings: dict | None = None
    obsidian_settings: dict | None = None
    claude_settings: dict | None = None
    workspace_settings: dict | None = None
    notification_settings: dict | None = None


class SettingsOut(BaseModel):
    theme: str
    language: str
    sidebar_collapsed: bool
    ai_settings: dict
    obsidian_settings: dict
    claude_settings: dict
    workspace_settings: dict
    notification_settings: dict

    model_config = {"from_attributes": True}
