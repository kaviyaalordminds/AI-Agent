import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KnowledgeSyncAction(str, enum.Enum):
    created = "created"
    updated = "updated"
    skipped = "skipped"


class KnowledgeSync(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Audit trail for the automatic Knowledge Maintenance Agent (see
    app/knowledge/sync_agent.py): one row per time a chat message (or other
    future trigger source) was assessed as durable knowledge and synced
    into the user's Obsidian vault — or explicitly skipped, with why.
    Lives in the application database, never inside the vault itself, per
    the "Obsidian stays the sole source of truth for knowledge content, the
    app database holds only *about* it" split already used by
    KnowledgeAnalysis and HistoryEntry."""

    __tablename__ = "knowledge_syncs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[KnowledgeSyncAction] = mapped_column(
        Enum(KnowledgeSyncAction, name="knowledge_sync_action"), nullable=False, index=True
    )
    note_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    user: Mapped["User"] = relationship()
