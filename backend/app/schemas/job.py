import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.generation_job import JobStatus, JobType


class CreateAudioJobRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice: str | None = None
    language: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    format: str = "wav"
    project_id: uuid.UUID | None = None


class JobOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    type: JobType
    provider: str | None
    status: JobStatus
    progress: int
    input_metadata: dict
    output_metadata: dict
    error: str | None
    error_type: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}
