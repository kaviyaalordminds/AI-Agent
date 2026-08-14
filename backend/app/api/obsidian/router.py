from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.base import utcnow
from app.database.session import get_db
from app.integrations.obsidian.base import ObsidianProvider
from app.integrations.obsidian.errors import InvalidNotePathError, NoteAlreadyExistsError, NoteNotFoundError
from app.integrations.obsidian.factory import get_obsidian_provider
from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.obsidian import (
    AppendNoteRequest,
    CreateNoteRequest,
    MoveNoteRequest,
    NoteDetailOut,
    NoteSummaryOut,
    UpdateNoteRequest,
    VaultStatusOut,
)
from app.security.sessions import get_current_user, require_csrf

router = APIRouter(prefix="/obsidian", tags=["obsidian"])


def _provider(user: User) -> ObsidianProvider:
    return get_obsidian_provider(user.id)


def _handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NoteNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except NoteAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except InvalidNotePathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _log_knowledge_update(db: Session, user: User, title: str) -> None:
    db.add(
        HistoryEntry(
            user_id=user.id,
            project_id=None,
            type=HistoryEntryType.knowledge_update,
            status=HistoryEntryStatus.completed,
            title=title,
            completed_at=utcnow(),
        )
    )
    db.commit()


@router.get("/status", response_model=VaultStatusOut)
def vault_status(user: User = Depends(get_current_user)):
    return VaultStatusOut.model_validate(_provider(user).status().__dict__)


@router.get("/notes", response_model=list[NoteSummaryOut])
def list_notes(
    folder: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=255),
    user: User = Depends(get_current_user),
):
    provider = _provider(user)
    if search:
        results = _handle(provider.search, search)
    else:
        results = _handle(provider.list_notes, folder)
    return [NoteSummaryOut.model_validate(r.__dict__) for r in results]


@router.get("/notes/{note_path:path}", response_model=NoteDetailOut)
def read_note(note_path: str, user: User = Depends(get_current_user)):
    detail = _handle(_provider(user).read_note, note_path)
    return NoteDetailOut.model_validate(detail.__dict__)


@router.post("/notes", response_model=NoteDetailOut, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: CreateNoteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    detail = _handle(_provider(user).create_note, payload.path, payload.content)
    _log_knowledge_update(db, user, f"Created note: {detail.title}")
    return NoteDetailOut.model_validate(detail.__dict__)


@router.put("/notes/{note_path:path}", response_model=NoteDetailOut)
def update_note(
    note_path: str,
    payload: UpdateNoteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    detail = _handle(_provider(user).update_note, note_path, payload.content)
    _log_knowledge_update(db, user, f"Updated note: {detail.title}")
    return NoteDetailOut.model_validate(detail.__dict__)


@router.post("/notes/{note_path:path}/append", response_model=NoteDetailOut)
def append_note(
    note_path: str,
    payload: AppendNoteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    detail = _handle(_provider(user).append_note, note_path, payload.content)
    _log_knowledge_update(db, user, f"Appended to note: {detail.title}")
    return NoteDetailOut.model_validate(detail.__dict__)


@router.post("/notes/{note_path:path}/move", response_model=NoteDetailOut)
def move_note(
    note_path: str,
    payload: MoveNoteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    detail = _handle(_provider(user).move_note, note_path, payload.new_path)
    _log_knowledge_update(db, user, f"Moved note to: {detail.title}")
    return NoteDetailOut.model_validate(detail.__dict__)


@router.delete("/notes/{note_path:path}", response_model=MessageResponse)
def delete_note(
    note_path: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    _handle(_provider(user).delete_note, note_path)
    _log_knowledge_update(db, user, f"Deleted note: {note_path}")
    return MessageResponse(message="Note deleted.")
