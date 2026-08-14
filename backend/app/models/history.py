import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class HistoryEntryType(str, enum.Enum):
    chat = "chat"
    image = "image"
    video = "video"
    audio = "audio"
    document = "document"
    website = "website"
    poster = "poster"
    logo = "logo"
    deployment = "deployment"
    knowledge_update = "knowledge_update"


class HistoryEntryStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class HistoryEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A record of one AI-agent/generation action. Written by the module
    that performs the action (chat, image generation, deployment, etc.) —
    none of those modules exist yet, so this table is legitimately empty
    until later phases start writing to it. No entries are ever seeded or
    fabricated for display purposes."""

    __tablename__ = "history_entries"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[HistoryEntryType] = mapped_column(
        Enum(HistoryEntryType, name="history_entry_type"), nullable=False, index=True
    )
    status: Mapped[HistoryEntryStatus] = mapped_column(
        Enum(HistoryEntryStatus, name="history_entry_status"),
        default=HistoryEntryStatus.queued,
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    output_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship()
    project: Mapped["Project | None"] = relationship()
