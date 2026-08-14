import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentFormat(str, enum.Enum):
    markdown = "markdown"
    docx = "docx"
    pdf = "pdf"


class DocumentStatus(str, enum.Enum):
    completed = "completed"
    failed = "failed"


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single AI-drafted document (Phase 7, Document Generation): the
    user's prompt is turned into real markdown content via Claude, then
    rendered to the requested file format and written through
    StorageProvider. Requires a configured Claude provider — see
    app/documents/generator.py — but the prompt itself is always persisted
    first, exactly like AI Chat and Knowledge Gap analysis, so a missing
    API key never loses the user's request."""

    __tablename__ = "documents"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[DocumentFormat] = mapped_column(Enum(DocumentFormat, name="document_format"), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, name="document_status"), nullable=False)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    """The drafted markdown content — kept even for docx/pdf outputs so
    the document can be previewed without re-downloading the binary."""
    storage_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    """StorageProvider reference to the rendered file, never a raw
    filesystem path exposed to the client — see app/api/documents/router.py."""
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User"] = relationship()
    project: Mapped["Project | None"] = relationship()
