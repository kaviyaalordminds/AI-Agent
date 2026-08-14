"""Claude-backed document drafting + real file rendering (Phase 7).

Follows the exact honesty contract established by AI Chat and Knowledge
Gap analysis: the user's prompt is persisted before any Claude call is
attempted, and if Claude isn't configured (or the call fails) the
document is recorded as failed with the real error — never a fabricated
draft, never a silently dropped request.
"""
import uuid

from sqlalchemy.orm import Session

from app.database.base import utcnow
from app.documents.render import render_docx, render_pdf
from app.integrations.claude.base import ClaudeProvider
from app.integrations.claude.errors import ProviderRequestError
from app.integrations.claude.utils import complete
from app.integrations.storage.base import StorageProvider
from app.integrations.storage.errors import StorageError
from app.models.document import Document, DocumentFormat, DocumentStatus
from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType
from app.models.project import Project
from app.models.user import User

_SYSTEM_PROMPT = """You are the Document Generation engine of the AI Agent Platform.
The user will describe a document they want drafted. Write the complete
document as clean Markdown: a single top-level "# Title" heading, then
"##"/"###" section headings, paragraphs, and "-"/numbered lists as
appropriate for the content. Write the real, complete document body —
do not describe what the document would contain, do not add commentary
before or after it, and do not wrap it in a code fence."""

_MAX_TITLE_CHARS = 255


def _derive_title(prompt: str, raw_content: str | None) -> str:
    if raw_content:
        for line in raw_content.splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped:
                return stripped[:_MAX_TITLE_CHARS]
    fallback = prompt.strip().splitlines()[0] if prompt.strip() else "Untitled document"
    return fallback[:_MAX_TITLE_CHARS]


def _record_failed_document(
    db: Session,
    user: User,
    project: Project | None,
    prompt: str,
    doc_format: DocumentFormat,
    error_detail: str,
) -> Document:
    document = Document(
        user_id=user.id,
        project_id=project.id if project else None,
        title=_derive_title(prompt, None),
        prompt=prompt,
        format=doc_format,
        status=DocumentStatus.failed,
        error=error_detail,
    )
    db.add(document)
    _log_history(db, user, project, document.title, HistoryEntryStatus.failed)
    db.commit()
    db.refresh(document)
    return document


def record_unavailable_document(
    db: Session, user: User, project: Project | None, prompt: str, doc_format: DocumentFormat, error_detail: str
) -> Document:
    """Provider couldn't even be constructed — persist the prompt anyway so
    it isn't lost, exactly like record_unavailable_turn/analysis do."""
    return _record_failed_document(db, user, project, prompt, doc_format, error_detail)


async def generate_document(
    db: Session,
    user: User,
    project: Project | None,
    claude_provider: ClaudeProvider,
    storage_provider: StorageProvider,
    prompt: str,
    doc_format: DocumentFormat,
) -> Document:
    try:
        raw_content = await complete(claude_provider, prompt, _SYSTEM_PROMPT)
    except ProviderRequestError as exc:
        return _record_failed_document(db, user, project, prompt, doc_format, str(exc))

    title = _derive_title(prompt, raw_content)

    if doc_format == DocumentFormat.docx:
        file_bytes = render_docx(raw_content, title)
        extension = "docx"
    elif doc_format == DocumentFormat.pdf:
        file_bytes = render_pdf(raw_content, title)
        extension = "pdf"
    else:
        file_bytes = raw_content.encode("utf-8")
        extension = "md"

    filename = f"{uuid.uuid4()}.{extension}"
    try:
        stored = storage_provider.write("documents", str(user.id), filename, file_bytes)
    except StorageError as exc:
        return _record_failed_document(db, user, project, prompt, doc_format, str(exc))

    document = Document(
        user_id=user.id,
        project_id=project.id if project else None,
        title=title,
        prompt=prompt,
        format=doc_format,
        status=DocumentStatus.completed,
        content=raw_content,
        storage_ref=stored.ref,
        size_bytes=stored.size_bytes,
    )
    db.add(document)
    _log_history(db, user, project, title, HistoryEntryStatus.completed)
    db.commit()
    db.refresh(document)
    return document


def _log_history(
    db: Session, user: User, project: Project | None, title: str, status: HistoryEntryStatus
) -> None:
    db.add(
        HistoryEntry(
            user_id=user.id,
            project_id=project.id if project else None,
            type=HistoryEntryType.document,
            status=status,
            title=f"Document: {title}",
            completed_at=utcnow() if status == HistoryEntryStatus.completed else None,
        )
    )
