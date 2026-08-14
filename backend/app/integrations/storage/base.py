"""StorageProvider abstraction.

Same pattern as EmailProvider/ClaudeProvider/ObsidianProvider: application
code never touches the filesystem (or, for a future S3/GCS-backed
provider, a cloud SDK) directly. It calls `StorageProvider.write(...)` /
`.read(...)` / `.delete(...)`, and `get_storage_provider()` decides which
concrete implementation to build from environment configuration. Postgres
stores only a reference (see storage/README.md's hybrid storage model) —
the actual bytes always live behind this interface.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StoredFile:
    ref: str
    """Provider-specific reference to the stored file (a relative path for
    the local provider; would be an object key/URL for a cloud provider).
    This, not the raw bytes, is what gets persisted in Postgres."""
    size_bytes: int


class StorageProvider(ABC):
    @abstractmethod
    def write(self, category: str, owner_id: str, filename: str, data: bytes) -> StoredFile:
        """Persist `data` under a path namespaced by category (e.g.
        "documents") and owner (typically a user id), and return a
        reference to it. Must raise on failure — never return a fake
        success."""
        raise NotImplementedError

    @abstractmethod
    def read(self, ref: str) -> bytes:
        """Return the raw bytes for a previously-written file. Raises
        FileNotFoundError if the reference no longer resolves to a file."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, ref: str) -> None:
        """Remove a previously-written file. A no-op (not an error) if the
        file is already gone."""
        raise NotImplementedError
