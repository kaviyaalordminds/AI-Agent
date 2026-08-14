import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.document import DocumentFormat, DocumentStatus


class CreateDocumentRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    format: DocumentFormat = DocumentFormat.markdown
    project_id: uuid.UUID | None = None

    @field_validator("prompt")
    @classmethod
    def _strip_prompt(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Describe the document you want in a bit more detail.")
        return v


class DocumentOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    project_name: str | None = None
    title: str
    prompt: str
    format: DocumentFormat
    status: DocumentStatus
    error: str | None
    content: str | None
    size_bytes: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
