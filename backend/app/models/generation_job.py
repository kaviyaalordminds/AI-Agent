import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class JobType(str, enum.Enum):
    audio = "audio"
    transcription = "transcription"
    image = "image"
    video = "video"
    voice_clone = "voice_clone"


class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class GenerationJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A long-running generation operation (audio/transcription/image/
    video/voice), run out-of-request-scope by the job queue (see
    app/jobs/) rather than blocking the HTTP request that created it.

    Document generation is intentionally NOT a job — it's fast enough
    (a Claude completion + local rendering) that the existing synchronous
    /api/documents endpoint stays simpler for callers with no real
    downside; this table is for the categories where blocking a request
    would be genuinely unacceptable, and where a local backend may not
    even be available (in which case the job still completes, honestly,
    as `failed` with a real error rather than hanging or crashing)."""

    __tablename__ = "generation_jobs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[JobType] = mapped_column(Enum(JobType, name="generation_job_type"), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="generation_job_status"), default=JobStatus.queued, nullable=False, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship()
    project: Mapped["Project | None"] = relationship()
