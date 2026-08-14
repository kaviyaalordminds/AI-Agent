import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.history import HistoryEntryStatus, HistoryEntryType


class HistoryEntryOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    project_name: str | None = None
    type: HistoryEntryType
    status: HistoryEntryStatus
    title: str
    output_ref: str | None
    duration_ms: int | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class HistoryListResponse(BaseModel):
    items: list[HistoryEntryOut]
    total: int
    page: int
    page_size: int


class UpdateHistoryEntryRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    project_id: uuid.UUID | None = None
    clear_project: bool = False

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be empty.")
        return v
