import re
from pathlib import Path

from app.integrations.storage.base import StorageProvider, StoredFile
from app.integrations.storage.errors import InvalidStoragePathError

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_segment(name: str, label: str) -> str:
    if not name or not _SAFE_SEGMENT.match(name) or name in (".", ".."):
        raise InvalidStoragePathError(f"Invalid {label} '{name}'.")
    return name


class LocalStorageProvider(StorageProvider):
    """Real, working storage: generated assets live as plain files under a
    root directory (see storage/README.md) — no external bucket/credentials
    required. A future S3Provider/GCSProvider would implement the same
    interface without any call site changing."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, category: str, owner_id: str, filename: str) -> Path:
        category = _validate_segment(category, "category")
        owner_id = _validate_segment(owner_id, "owner id")
        filename = _validate_segment(filename, "filename")
        resolved = (self.root / category / owner_id / filename).resolve()
        if self.root not in resolved.parents:
            raise InvalidStoragePathError("Resolved path escapes the storage root.")
        return resolved

    def _resolve_ref(self, ref: str) -> Path:
        normalized = ref.strip().replace("\\", "/")
        if normalized.startswith("/") or normalized.startswith("~") or ".." in normalized.split("/"):
            raise InvalidStoragePathError("Storage reference must be a relative path with no '..'.")
        resolved = (self.root / normalized).resolve()
        if self.root not in resolved.parents and resolved != self.root:
            raise InvalidStoragePathError("Storage reference escapes the storage root.")
        return resolved

    def write(self, category: str, owner_id: str, filename: str, data: bytes) -> StoredFile:
        path = self._resolve(category, owner_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        ref = path.relative_to(self.root).as_posix()
        return StoredFile(ref=ref, size_bytes=len(data))

    def read(self, ref: str) -> bytes:
        path = self._resolve_ref(ref)
        if not path.is_file():
            raise FileNotFoundError(f"No stored file at '{ref}'.")
        return path.read_bytes()

    def delete(self, ref: str) -> None:
        path = self._resolve_ref(ref)
        path.unlink(missing_ok=True)
