class StorageError(Exception):
    """Base class for storage provider failures."""


class InvalidStoragePathError(StorageError):
    """Raised when a category/owner id/filename would escape the storage root."""
