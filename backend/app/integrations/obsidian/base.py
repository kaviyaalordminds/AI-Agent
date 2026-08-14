"""ObsidianProvider abstraction.

Same pattern as EmailProvider and ClaudeProvider: application code calls
this interface, never the filesystem (or, for a future MCP/REST-backed
provider, an HTTP client) directly. `get_obsidian_provider()` decides the
concrete implementation from environment configuration.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NoteSummary:
    path: str
    title: str
    folder: str
    excerpt: str
    tags: list[str]
    links: list[str]
    updated_at: datetime
    size_bytes: int


@dataclass
class NoteDetail:
    path: str
    title: str
    content: str
    tags: list[str]
    links: list[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class VaultStatus:
    configured: bool
    connected: bool
    provider: str
    vault_path: str
    note_count: int
    detail: str
    folders: list[str] = field(default_factory=list)


@dataclass
class NoteMetadata:
    path: str
    title: str
    folder: str
    tags: list[str]
    links: list[str]
    created_at: datetime
    updated_at: datetime
    size_bytes: int


class ObsidianProvider(ABC):
    """This is also the platform's KnowledgeProvider implementation (see
    KNOWLEDGE_PROVIDER in app/core/config.py) — Obsidian is currently the
    only knowledge backend, so a separate KnowledgeProvider ABC would just
    duplicate this one. get_knowledge_provider() in factory.py is a
    documented alias of get_obsidian_provider() for callers that want the
    general-purpose name."""

    @abstractmethod
    def status(self) -> VaultStatus:
        raise NotImplementedError

    @abstractmethod
    def list_notes(self, folder: str | None = None) -> list[NoteSummary]:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str) -> list[NoteSummary]:
        raise NotImplementedError

    @abstractmethod
    def read_note(self, path: str) -> NoteDetail:
        raise NotImplementedError

    @abstractmethod
    def create_note(self, path: str, content: str) -> NoteDetail:
        raise NotImplementedError

    @abstractmethod
    def update_note(self, path: str, content: str) -> NoteDetail:
        raise NotImplementedError

    @abstractmethod
    def append_note(self, path: str, content: str) -> NoteDetail:
        raise NotImplementedError

    @abstractmethod
    def delete_note(self, path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def move_note(self, path: str, new_path: str) -> NoteDetail:
        raise NotImplementedError

    @abstractmethod
    def get_metadata(self, path: str) -> NoteMetadata:
        raise NotImplementedError
