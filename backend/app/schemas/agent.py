import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.conversation import AgentMode, MessageRole


class CreateConversationRequest(BaseModel):
    mode: AgentMode = AgentMode.chat
    project_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=255)


class UpdateConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be empty.")
        return v


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty.")
        return v


class MessageOut(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: uuid.UUID
    mode: AgentMode
    project_id: uuid.UUID | None
    project_name: str | None = None
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class ClaudeStatusOut(BaseModel):
    configured: bool
    provider: str
    model: str | None
    detail: str
