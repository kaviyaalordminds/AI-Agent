import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType
from app.models.project import Project
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.history import HistoryEntryOut, HistoryListResponse, UpdateHistoryEntryRequest
from app.security.sessions import get_current_user, require_csrf

router = APIRouter(prefix="/history", tags=["history"])


def _get_owned_entry(db: Session, user: User, entry_id: uuid.UUID) -> HistoryEntry:
    entry = (
        db.query(HistoryEntry)
        .filter(HistoryEntry.id == entry_id, HistoryEntry.user_id == user.id)
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History entry not found.")
    return entry


def _to_out(entry: HistoryEntry) -> HistoryEntryOut:
    out = HistoryEntryOut.model_validate(entry)
    out.project_name = entry.project.name if entry.project else None
    return out


@router.get("", response_model=HistoryListResponse)
def list_history(
    type: HistoryEntryType | None = Query(default=None),
    status_filter: HistoryEntryStatus | None = Query(default=None, alias="status"),
    project_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None, max_length=255),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(HistoryEntry).filter(HistoryEntry.user_id == user.id)

    if type is not None:
        query = query.filter(HistoryEntry.type == type)
    if status_filter is not None:
        query = query.filter(HistoryEntry.status == status_filter)
    if project_id is not None:
        query = query.filter(HistoryEntry.project_id == project_id)
    if search:
        query = query.filter(HistoryEntry.title.ilike(f"%{search}%"))
    if date_from is not None:
        query = query.filter(HistoryEntry.created_at >= date_from)
    if date_to is not None:
        query = query.filter(HistoryEntry.created_at <= date_to)

    total = query.with_entities(func.count(HistoryEntry.id)).scalar()
    items = (
        query.order_by(HistoryEntry.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return HistoryListResponse(
        items=[_to_out(e) for e in items], total=total, page=page, page_size=page_size
    )


@router.patch("/{entry_id}", response_model=HistoryEntryOut)
def update_history_entry(
    entry_id: uuid.UUID,
    payload: UpdateHistoryEntryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    entry = _get_owned_entry(db, user, entry_id)

    if payload.title is not None:
        entry.title = payload.title

    if payload.clear_project:
        entry.project_id = None
    elif payload.project_id is not None:
        owned_project = (
            db.query(Project)
            .filter(Project.id == payload.project_id, Project.user_id == user.id)
            .first()
        )
        if owned_project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Target project not found."
            )
        entry.project_id = owned_project.id

    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _to_out(entry)


@router.delete("/{entry_id}", response_model=MessageResponse)
def delete_history_entry(
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    entry = _get_owned_entry(db, user, entry_id)
    db.delete(entry)
    db.commit()
    return MessageResponse(message="History entry deleted.")
