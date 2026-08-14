import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """User preferences.

    Only `theme`, `language`, and `sidebar_collapsed` are acted on by the
    Phase 1/2 foundation build. The remaining JSON blocks (ai, obsidian,
    claude, workspace, notifications) exist now as real, persisted, editable
    settings so later phases (Obsidian/MCP/Claude providers, AI Agent,
    creative studios) can read/write them without a schema migration —
    but nothing in this phase claims those integrations are configured or
    functional; the connection-status endpoints added in later phases are
    what will report real state.
    """

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    theme: Mapped[str] = mapped_column(String(16), default="dark", nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    sidebar_collapsed: Mapped[bool] = mapped_column(default=False, nullable=False)

    ai_settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    obsidian_settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    claude_settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    workspace_settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    notification_settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    user: Mapped["User"] = relationship(back_populates="settings")
