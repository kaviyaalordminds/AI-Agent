from pathlib import Path

from app.core.config import get_settings
from app.integrations.storage.base import StorageProvider
from app.integrations.storage.local_provider import LocalStorageProvider


def get_storage_provider() -> StorageProvider:
    """Deliberately not cached — mirrors get_obsidian_provider(), so tests
    (and any future runtime reconfiguration) that point STORAGE_ROOT at a
    different directory take effect immediately rather than being stuck
    with whichever root was resolved on first use."""
    settings = get_settings()

    if settings.storage_provider == "local":
        return LocalStorageProvider(Path(settings.storage_root))

    raise ValueError(f"Unknown STORAGE_PROVIDER '{settings.storage_provider}'.")
