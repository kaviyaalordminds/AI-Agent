import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.database.session import get_db
from app.documents.generator import generate_document, record_unavailable_document
from app.integrations.claude.errors import ProviderNotConfiguredError
from app.integrations.claude.factory import get_claude_provider
from app.integrations.storage.factory import get_storage_provider
from app.models.document import Document, DocumentFormat
from app.models.project import Project
from app.models.user import User
from app.schemas.document import CreateDocumentRequest, DocumentOut
from app.security.rate_limit import enforce_rate_limit
from app.security.sessions import get_current_user, require_csrf

router = APIRouter(prefix="/documents", tags=["documents"])

_CONTENT_TYPES = {
    DocumentFormat.markdown: ("text/markdown; charset=utf-8", "md"),
    DocumentFormat.docx: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    ),
    DocumentFormat.pdf: ("application/pdf", "pdf"),
    DocumentFormat.pptx: (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "pptx",
    ),
    DocumentFormat.xlsx: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
}


def _to_document_out(document: Document) -> DocumentOut:
    out = DocumentOut.model_validate(document)
    out.project_name = document.project.name if document.project else None
    return out


def _get_owned_document(db: Session, user: User, document_id: uuid.UUID) -> Document:
    document = db.query(Document).filter(Document.id == document_id, Document.user_id == user.id).first()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document


@router.get("", response_model=list[DocumentOut])
def list_documents(
    project_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # joinedload avoids an N+1 (one SELECT per row) that _to_document_out's
    # document.project.name lazy-load would otherwise trigger.
    query = db.query(Document).options(joinedload(Document.project)).filter(Document.user_id == user.id)
    if project_id is not None:
        query = query.filter(Document.project_id == project_id)
    documents = query.order_by(Document.created_at.desc()).all()
    return [_to_document_out(d) for d in documents]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _to_document_out(_get_owned_document(db, user, document_id))


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def create_document(
    payload: CreateDocumentRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)

    project = None
    if payload.project_id is not None:
        project = db.query(Project).filter(Project.id == payload.project_id, Project.user_id == user.id).first()
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    try:
        claude_provider = get_claude_provider()
    except ProviderNotConfiguredError as exc:
        record_unavailable_document(db, user, project, payload.prompt, payload.format, str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    storage_provider = get_storage_provider()
    document = await generate_document(
        db, user, project, claude_provider, storage_provider, payload.prompt, payload.format
    )
    return _to_document_out(document)


@router.get("/{document_id}/download")
def download_document(document_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = _get_owned_document(db, user, document_id)
    if not document.storage_ref:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document has no generated file to download.",
        )

    storage_provider = get_storage_provider()
    try:
        data = storage_provider.read(document.storage_ref)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated file no longer exists.")

    media_type, extension = _CONTENT_TYPES[document.format]
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in document.title).strip() or "document"
    filename = f"{safe_title}.{extension}"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    document = _get_owned_document(db, user, document_id)
    if document.storage_ref:
        storage_provider = get_storage_provider()
        storage_provider.delete(document.storage_ref)
    db.delete(document)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
