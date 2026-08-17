import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.website import WebsiteStatus

WEBSITE_STYLES = ("modern", "minimal", "bold", "corporate", "playful", "3d")


class CreateWebsiteRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    prompt: str = Field(min_length=3, max_length=2000)
    style: Literal["modern", "minimal", "bold", "corporate", "playful", "3d"] = "modern"
    pages: list[str] = Field(default_factory=lambda: ["Home"], min_length=1, max_length=12)
    project_id: uuid.UUID | None = None

    @field_validator("prompt")
    @classmethod
    def _strip_prompt(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Describe the website you want in a bit more detail.")
        return v

    @field_validator("pages")
    @classmethod
    def _clean_pages(cls, v: list[str]) -> list[str]:
        cleaned = [p.strip() for p in v if p.strip()]
        if not cleaned:
            raise ValueError("List at least one page.")
        return cleaned[:12]


class WebsitePageOut(BaseModel):
    name: str
    path: str
    size_bytes: int


class WebsiteOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    project_name: str | None = None
    name: str
    prompt: str
    style: str
    status: WebsiteStatus
    error: str | None
    pages: list[WebsitePageOut]
    deployment_provider: str | None
    deployment_storage_ref: str | None
    deployment_live_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DeployWebsiteResponse(BaseModel):
    provider: str
    downloadable: bool
    live_url: str | None
