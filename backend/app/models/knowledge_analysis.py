import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KnowledgeAnalysisStatus(str, enum.Enum):
    completed = "completed"
    failed = "failed"


class KnowledgeAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single gap-analysis run (spec section 22): given a query like
    'Build a manufacturing HRMS', search the vault for related notes, ask
    Claude to compare the request against what's already there, and
    persist the structured result. Requires a configured Claude provider —
    see app/knowledge/gap_analysis.py."""

    __tablename__ = "knowledge_analyses"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[KnowledgeAnalysisStatus] = mapped_column(
        Enum(KnowledgeAnalysisStatus, name="knowledge_analysis_status"), nullable=False
    )
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    existing_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_items: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    recommended_additions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    duplicate_notes: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    outdated_notes: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship()
    project: Mapped["Project | None"] = relationship()
