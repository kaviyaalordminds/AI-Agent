import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.base import utcnow
from app.database.session import get_db
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.project import CreateProjectRequest, ProjectOut, UpdateProjectRequest
from app.security.sessions import get_current_user, require_csrf

router = APIRouter(prefix="/projects", tags=["projects"])


def _get_owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    project = (
        db.query(Project).filter(Project.id == project_id, Project.user_id == user.id).first()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(
    status_filter: Literal["active", "archived", "all"] = Query("active", alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Project).filter(Project.user_id == user.id)
    if status_filter != "all":
        query = query.filter(Project.status == ProjectStatus(status_filter))
    projects = query.order_by(Project.updated_at.desc()).all()
    return [ProjectOut.model_validate(p) for p in projects]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: CreateProjectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    project = Project(user_id=user.id, name=payload.name, description=payload.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    project = _get_owned_project(db, user, project_id)
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: uuid.UUID,
    payload: UpdateProjectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    project = _get_owned_project(db, user, project_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(project, field, value)
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.post("/{project_id}/archive", response_model=ProjectOut)
def archive_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    project = _get_owned_project(db, user, project_id)
    project.status = ProjectStatus.archived
    project.archived_at = utcnow()
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.post("/{project_id}/unarchive", response_model=ProjectOut)
def unarchive_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    project = _get_owned_project(db, user, project_id)
    project.status = ProjectStatus.active
    project.archived_at = None
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.post("/{project_id}/duplicate", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def duplicate_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    original = _get_owned_project(db, user, project_id)
    copy = Project(
        user_id=user.id,
        name=f"{original.name} (copy)",
        description=original.description,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return ProjectOut.model_validate(copy)


@router.delete("/{project_id}", response_model=MessageResponse)
def delete_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    project = _get_owned_project(db, user, project_id)
    db.delete(project)
    db.commit()
    return MessageResponse(message="Project deleted.")
