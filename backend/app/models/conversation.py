import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AgentMode(str, enum.Enum):
    chat = "chat"
    knowledge = "knowledge"
    create = "create"
    project = "project"
    research = "research"
    developer = "developer"
    automation = "automation"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mode: Mapped[AgentMode] = mapped_column(Enum(AgentMode, name="agent_mode"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    user: Mapped["User"] = relationship()
    project: Mapped["Project | None"] = relationship()
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, doc="Set when an assistant turn failed instead of completing."
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
