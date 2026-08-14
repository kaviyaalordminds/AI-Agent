class VaultError(Exception):
    """Base class for vault/Obsidian integration failures."""


class InvalidNotePathError(VaultError):
    """Raised for a note path that's malformed, escapes the vault root, or
    doesn't end in .md. Never silently coerced — callers must fix the path."""


class NoteNotFoundError(VaultError):
    """Raised when reading/updating/appending/deleting/moving a note that
    doesn't exist."""


class NoteAlreadyExistsError(VaultError):
    """Raised by create when a note already exists at that path (use update
    or append instead)."""
