"""Persists a structured (non-AI) Word/PowerPoint/Excel generation as a
Document row, reusing the exact same table, storage flow, and History
logging as the Claude-drafted /api/documents flow (see
app/documents/generator.py) — a Document row doesn't care whether its
content came from an AI draft or caller-supplied structure, only what
format the resulting file is. This keeps /api/documents/{id}/download,
list, and delete working unmodified for these new formats.
"""
import uuid
from typing import Callable

from sqlalchemy.orm import Session

from app.database.base import utcnow
from app.integrations.storage.base import StorageProvider
from app.integrations.storage.errors import StorageError
from app.models.document import Document, DocumentFormat, DocumentStatus
from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType
from app.models.project import Project
from app.models.user import User


def generate_structured_document(
    db: Session,
    user: User,
    project: Project | None,
    storage_provider: StorageProvider,
    title: str,
    doc_format: DocumentFormat,
    extension: str,
    kind_label: str,
    render: Callable[[], bytes],
) -> Document:
    """`render` is called eagerly (no external network calls are ever
    involved for these formats) and any failure is recorded on the
    Document row as `failed` rather than raised past a lost request."""
    prompt_summary = f"Structured {kind_label} document: {title}"

    try:
        file_bytes = render()
    except Exception as exc:
        return _record_failed(
            db, user, project, title, prompt_summary, doc_format, kind_label, f"Could not render the document: {exc}"
        )

    filename = f"{uuid.uuid4()}.{extension}"
    try:
        stored = storage_provider.write("documents", str(user.id), filename, file_bytes)
    except StorageError as exc:
        return _record_failed(db, user, project, title, prompt_summary, doc_format, kind_label, str(exc))

    document = Document(
        user_id=user.id,
        project_id=project.id if project else None,
        title=title,
        prompt=prompt_summary,
        format=doc_format,
        status=DocumentStatus.completed,
        storage_ref=stored.ref,
        size_bytes=stored.size_bytes,
    )
    db.add(document)
    _log_history(db, user, project, kind_label, title, HistoryEntryStatus.completed)
    db.commit()
    db.refresh(document)
    return document


def _record_failed(
    db: Session,
    user: User,
    project: Project | None,
    title: str,
    prompt_summary: str,
    doc_format: DocumentFormat,
    kind_label: str,
    error_detail: str,
) -> Document:
    document = Document(
        user_id=user.id,
        project_id=project.id if project else None,
        title=title,
        prompt=prompt_summary,
        format=doc_format,
        status=DocumentStatus.failed,
        error=error_detail,
    )
    db.add(document)
    _log_history(db, user, project, kind_label, title, HistoryEntryStatus.failed)
    db.commit()
    db.refresh(document)
    return document


def _log_history(
    db: Session, user: User, project: Project | None, kind_label: str, title: str, status: HistoryEntryStatus
) -> None:
    db.add(
        HistoryEntry(
            user_id=user.id,
            project_id=project.id if project else None,
            type=HistoryEntryType.document,
            status=status,
            title=f"{kind_label.capitalize()}: {title}",
            completed_at=utcnow() if status == HistoryEntryStatus.completed else None,
        )
    )
