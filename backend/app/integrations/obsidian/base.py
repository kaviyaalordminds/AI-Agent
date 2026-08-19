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
    # The fully-resolved, absolute path this provider actually reads and
    # writes — never a raw/unresolved config value. Compare against
    # configured_path below: they should always be equal in single-vault
    # (OBSIDIAN_VAULT_PATH) mode, since that mode never appends a user id
    # or otherwise transforms the configured value.
    vault_path: str
    note_count: int
    detail: str
    folders: list[str] = field(default_factory=list)
    # The raw path this provider was constructed from, before resolution —
    # exactly what OBSIDIAN_VAULT_PATH (or the per-user default) said, so a
    # mismatch between this and vault_path above is immediately visible
    # rather than hidden inside a resolved-only value.
    configured_path: str = ""
    exists: bool = False
    is_directory: bool = False
    # Optional OBSIDIAN_VAULT_ID cross-check (see
    # app/integrations/obsidian/vault_identity.py) — vault_id is only
    # populated when OBSIDIAN_VAULT_ID is configured; vault_id_check is
    # "verified" | "mismatch" | "unverifiable" and vault_id_detail explains
    # why. None/None/None when no vault id is configured at all.
    vault_id: str | None = None
    vault_id_check: str | None = None
    vault_id_detail: str | None = None


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
