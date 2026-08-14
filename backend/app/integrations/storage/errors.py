class StorageError(Exception):
    """Base class for storage provider failures."""


class InvalidStoragePathError(StorageError):
    """Raised when a category/owner id/filename would escape the storage root."""


class FileTooLargeError(StorageError):
    """Raised when written data exceeds MAX_UPLOAD_FILE_SIZE_MB — a
    technical abuse-protection limit (see app/core/config.py), not a
    user-credit restriction."""
