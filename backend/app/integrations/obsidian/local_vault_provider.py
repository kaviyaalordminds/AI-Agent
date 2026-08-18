import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from app.integrations.obsidian.base import NoteDetail, NoteMetadata, NoteSummary, ObsidianProvider, VaultStatus
from app.integrations.obsidian.errors import InvalidNotePathError, NoteAlreadyExistsError, NoteNotFoundError
from app.integrations.obsidian.parsing import derive_excerpt, derive_title, extract_links, extract_tags
from app.integrations.obsidian.vault_identity import verify_vault_id

logger = logging.getLogger("integrations.obsidian")

DEFAULT_FOLDERS = [
    "00-System",
    "01-Knowledge",
    "02-Projects",
    "03-Resources",
    "04-Tasks",
    "05-Ideas",
    "06-Generated",
    "07-Research",
    "08-Reports",
    "09-AI-Memory",
]

_WELCOME_NOTE = """# Welcome to your Shadow AI vault

This vault is your knowledge layer. Shadow AI reads from and writes to
it — notes here, not the application database, are what makes the agent
"know" your projects and domain.

## Structure

- **00-System** — this note and other vault-level configuration
- **01-Knowledge** — durable reference knowledge (organize into subfolders as you like)
- **02-Projects** — one subfolder per project, mirroring your Projects in the app
- **03-Resources** — links, references, source material
- **04-Tasks** — task notes
- **05-Ideas** — rough notes and drafts
- **06-Generated** — content Shadow AI generates on your behalf
- **07-Research** — research notes (used by Research mode once knowledge analysis ships)
- **08-Reports** — generated reports
- **09-AI-Memory** — long-term memory the agent keeps about you and your work

Use `[[wiki links]]` to connect notes and `#tags` to categorize them — Shadow AI parses both.
"""

_STOPWORDS = {
    "a", "about", "after", "all", "an", "and", "any", "are", "as", "at", "be", "but", "by",
    "can", "could", "did", "do", "does", "for", "from", "had", "has", "have", "how", "i",
    "if", "in", "into", "is", "it", "its", "me", "my", "of", "on", "or", "our", "please",
    "she", "so", "some", "tell", "that", "the", "their", "them", "then", "there", "these",
    "they", "this", "to", "us", "was", "we", "were", "what", "when", "where", "which",
    "who", "will", "with", "would", "you", "your",
}


def validate_obsidian_path(vault_root: Path, target_path: str, *, must_exist: bool | None = None) -> Path:
    """The single, backend-enforced guard against writing outside the
    configured Obsidian vault. Every note read/write in this module funnels
    through here — never trust a path handed in from a request body or the
    frontend; this always re-resolves it against `vault_root` and rejects
    anything that isn't a real descendant of it (absolute paths, drive
    letters, home-relative '~', and '..' traversal segments included), so a
    frontend-supplied path can never point outside the vault regardless of
    what the caller sends.

    Raises InvalidNotePathError for anything invalid/escaping;
    NoteNotFoundError / NoteAlreadyExistsError when `must_exist` is given
    and the resolved file's existence doesn't match it.
    """
    if not target_path or not target_path.strip():
        raise InvalidNotePathError("Note path is required.")
    normalized = target_path.strip().replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("~") or ":" in normalized:
        raise InvalidNotePathError("Note path must be relative to the vault.")
    if not normalized.endswith(".md"):
        raise InvalidNotePathError("Note path must end in .md")
    parts = normalized.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise InvalidNotePathError("Note path may not contain '..' or empty segments.")

    vault_root = vault_root.resolve()
    resolved = (vault_root / normalized).resolve()
    if resolved != vault_root and vault_root not in resolved.parents:
        raise InvalidNotePathError("Note path escapes the vault.")

    if must_exist is True and not resolved.is_file():
        raise NoteNotFoundError(f"No note at '{target_path}'.")
    if must_exist is False and resolved.exists():
        raise NoteAlreadyExistsError(f"A note already exists at '{target_path}'.")
    return resolved


def provision_vault(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for folder in DEFAULT_FOLDERS:
        (root / folder).mkdir(parents=True, exist_ok=True)
    welcome_path = root / "00-System" / "Welcome.md"
    if not welcome_path.exists():
        welcome_path.write_text(_WELCOME_NOTE, encoding="utf-8")


class LocalVaultProvider(ObsidianProvider):
    """Real Obsidian-vault-compatible storage: a plain directory of
    markdown files. No Obsidian.app process is required — a vault is just
    files, and this is a genuine implementation of vault operations, not a
    mock standing in for one."""

    def __init__(self, root: Path, vault_id: str | None = None) -> None:
        self.root = root.resolve()
        self.vault_id = vault_id

    def _resolve(self, path: str, must_exist: bool | None = None) -> Path:
        return validate_obsidian_path(self.root, path, must_exist=must_exist)

    def _to_summary(self, file_path: Path) -> NoteSummary:
        rel = file_path.relative_to(self.root).as_posix()
        content = file_path.read_text(encoding="utf-8", errors="replace")
        stat = file_path.stat()
        return NoteSummary(
            path=rel,
            title=derive_title(rel, content),
            folder=rel.rsplit("/", 1)[0] if "/" in rel else "",
            excerpt=derive_excerpt(content),
            tags=extract_tags(content),
            links=extract_links(content),
            updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            size_bytes=stat.st_size,
        )

    def _to_detail(self, file_path: Path) -> NoteDetail:
        rel = file_path.relative_to(self.root).as_posix()
        content = file_path.read_text(encoding="utf-8", errors="replace")
        stat = file_path.stat()
        return NoteDetail(
            path=rel,
            title=derive_title(rel, content),
            content=content,
            tags=extract_tags(content),
            links=extract_links(content),
            created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
            updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        )

    def _all_note_files(self) -> list[Path]:
        return sorted(p for p in self.root.rglob("*.md") if p.is_file())

    def _searchable_note_files(self) -> list[Path]:
        # 00-System holds vault-internal documentation (e.g. the
        # auto-generated welcome note), not user knowledge — it shouldn't
        # show up in search results or get fed to the AI as "relevant
        # notes", where its generic vocabulary would otherwise dominate.
        return [p for p in self._all_note_files() if p.relative_to(self.root).parts[0] != "00-System"]

    def status(self) -> VaultStatus:
        try:
            note_count = len(self._all_note_files())
            connected = True
            detail = f"Connected to local vault at {self.root} ({note_count} notes)."
        except OSError as exc:
            note_count = 0
            connected = False
            detail = f"Vault path is not accessible: {exc}"

        vault_id_check = None
        vault_id_detail = None
        if self.vault_id:
            check = verify_vault_id(self.vault_id, self.root)
            vault_id_check = check.status
            vault_id_detail = check.detail

        return VaultStatus(
            configured=True,
            connected=connected,
            provider="local_vault",
            vault_path=str(self.root),
            note_count=note_count,
            detail=detail,
            folders=DEFAULT_FOLDERS,
            vault_id=self.vault_id,
            vault_id_check=vault_id_check,
            vault_id_detail=vault_id_detail,
        )

    def list_notes(self, folder: str | None = None) -> list[NoteSummary]:
        base = self.root
        if folder:
            base = (self.root / folder).resolve()
            if base != self.root and self.root not in base.parents:
                raise InvalidNotePathError("Folder escapes the vault.")
        if not base.exists():
            return []
        files = sorted((p for p in base.rglob("*.md") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
        return [self._to_summary(p) for p in files]

    def search(self, query: str) -> list[NoteSummary]:
        """Token-overlap keyword search: chat messages and search boxes are
        natural-language text, not exact phrases, so this scores notes by
        how many significant words they share with the query — an exact
        phrase match anywhere is additionally boosted. This is explicitly
        NOT semantic search (see prompts.py callers), just real, honest
        keyword matching."""
        query_lower = query.strip().lower()
        if not query_lower:
            return []
        tokens = [t for t in re.findall(r"[a-z0-9][a-z0-9\-']*", query_lower) if t not in _STOPWORDS]
        if not tokens:
            tokens = [query_lower]

        results: list[tuple[int, float, NoteSummary]] = []
        for file_path in self._searchable_note_files():
            summary = self._to_summary(file_path)
            content_lower = file_path.read_text(encoding="utf-8", errors="replace").lower()
            title_lower = summary.title.lower()
            tags_lower = {t.lower() for t in summary.tags}

            score = 0
            for token in set(tokens):
                if token in title_lower:
                    score += 3
                if token in tags_lower:
                    score += 2
                if token in content_lower:
                    score += 1
            if title_lower.find(query_lower) != -1 or content_lower.find(query_lower) != -1:
                score += 4

            if score == 0:
                continue
            results.append((score, summary.updated_at.timestamp(), summary))

        results.sort(key=lambda triple: (triple[0], triple[1]), reverse=True)
        return [summary for _score, _ts, summary in results]

    def read_note(self, path: str) -> NoteDetail:
        file_path = self._resolve(path, must_exist=True)
        return self._to_detail(file_path)

    def create_note(self, path: str, content: str) -> NoteDetail:
        file_path = self._resolve(path, must_exist=False)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return self._to_detail(file_path)

    def update_note(self, path: str, content: str) -> NoteDetail:
        file_path = self._resolve(path, must_exist=True)
        file_path.write_text(content, encoding="utf-8")
        return self._to_detail(file_path)

    def append_note(self, path: str, content: str) -> NoteDetail:
        file_path = self._resolve(path)
        if file_path.is_file():
            existing = file_path.read_text(encoding="utf-8")
            separator = "\n\n" if existing and not existing.endswith("\n\n") else ""
            file_path.write_text(existing + separator + content, encoding="utf-8")
        else:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
        return self._to_detail(file_path)

    def delete_note(self, path: str) -> None:
        file_path = self._resolve(path, must_exist=True)
        file_path.unlink()

    def move_note(self, path: str, new_path: str) -> NoteDetail:
        src = self._resolve(path, must_exist=True)
        dst = self._resolve(new_path, must_exist=False)
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return self._to_detail(dst)

    def get_metadata(self, path: str) -> NoteMetadata:
        file_path = self._resolve(path, must_exist=True)
        summary = self._to_summary(file_path)
        stat = file_path.stat()
        return NoteMetadata(
            path=summary.path,
            title=summary.title,
            folder=summary.folder,
            tags=summary.tags,
            links=summary.links,
            created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
            updated_at=summary.updated_at,
            size_bytes=summary.size_bytes,
        )
