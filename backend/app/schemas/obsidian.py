from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class NoteSummaryOut(BaseModel):
    path: str
    title: str
    folder: str
    excerpt: str
    tags: list[str]
    links: list[str]
    updated_at: datetime
    size_bytes: int


class NoteDetailOut(BaseModel):
    path: str
    title: str
    content: str
    tags: list[str]
    links: list[str]
    created_at: datetime
    updated_at: datetime


class VaultStatusOut(BaseModel):
    configured: bool
    connected: bool
    provider: str
    vault_path: str
    note_count: int
    detail: str
    folders: list[str]
    configured_path: str = ""
    exists: bool = False
    is_directory: bool = False
    vault_id: str | None = None
    vault_id_check: str | None = None
    vault_id_detail: str | None = None


class CreateNoteRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    content: str = ""

    @field_validator("path")
    @classmethod
    def _strip_path(cls, v: str) -> str:
        return v.strip()


class UpdateNoteRequest(BaseModel):
    content: str


class AppendNoteRequest(BaseModel):
    content: str = Field(min_length=1)


class MoveNoteRequest(BaseModel):
    new_path: str = Field(min_length=1, max_length=1024)

    @field_validator("new_path")
    @classmethod
    def _strip_path(cls, v: str) -> str:
        return v.strip()
