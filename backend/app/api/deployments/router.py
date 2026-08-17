"""Deployments module: a first-class, trackable deployment record and
lifecycle (create -> deploy -> active/failed -> stop/redeploy/delete),
distinct from Website Studio's own inline one-shot "Deploy" button
(app/api/websites/router.py's POST /websites/{id}/deploy, left
unchanged). A generated Website is the only real deployable source this
codebase produces (a static HTML/CSS/JS project) — "3D Website" is a
display-level distinction (Website.style == "3d"), not a second source
model. Deploying reuses the exact same DeploymentProvider Website Studio
already uses (see app/integrations/deployment/) — no parallel provider
architecture, no fabricated infrastructure.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.database.base import utcnow
from app.database.session import get_db
from app.integrations.deployment.factory import get_deployment_provider
from app.integrations.generation.errors import GenerationProviderError
from app.integrations.storage.factory import get_storage_provider
from app.models.deployment import Deployment, DeploymentEnvironment, DeploymentStatus
from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType
from app.models.user import User
from app.models.website import Website, WebsiteStatus
from app.schemas.deployment import CreateDeploymentRequest, DeploymentOut, UpdateDeploymentRequest
from app.security.rate_limit import enforce_rate_limit
from app.security.sessions import get_current_user, require_csrf

router = APIRouter(prefix="/deployments", tags=["deployments"])


def _to_deployment_out(deployment: Deployment) -> DeploymentOut:
    website = deployment.website
    return DeploymentOut(
        id=deployment.id,
        project_id=deployment.project_id,
        project_name=deployment.project.name if deployment.project else None,
        website_id=deployment.website_id,
        website_name=website.name,
        deployment_type="website_3d" if website.style == "3d" else "website",
        name=deployment.name,
        environment=deployment.environment,
        status=deployment.status,
        provider=deployment.provider,
        live_url=deployment.live_url,
        downloadable=deployment.storage_ref is not None,
        error=deployment.error,
        created_at=deployment.created_at,
        updated_at=deployment.updated_at,
        deployed_at=deployment.deployed_at,
    )


def _get_owned_deployment(db: Session, user: User, deployment_id: uuid.UUID) -> Deployment:
    deployment = (
        db.query(Deployment)
        .options(joinedload(Deployment.website), joinedload(Deployment.project))
        .filter(Deployment.id == deployment_id, Deployment.user_id == user.id)
        .first()
    )
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found.")
    return deployment


def _get_owned_website(db: Session, user: User, website_id: uuid.UUID) -> Website:
    website = db.query(Website).filter(Website.id == website_id, Website.user_id == user.id).first()
    if website is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found.")
    return website


@router.get("", response_model=list[DeploymentOut])
def list_deployments(
    project_id: uuid.UUID | None = Query(default=None),
    status_filter: DeploymentStatus | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Deployment)
        .options(joinedload(Deployment.website), joinedload(Deployment.project))
        .filter(Deployment.user_id == user.id)
    )
    if project_id is not None:
        query = query.filter(Deployment.project_id == project_id)
    if status_filter is not None:
        query = query.filter(Deployment.status == status_filter)
    deployments = query.order_by(Deployment.created_at.desc()).all()
    return [_to_deployment_out(d) for d in deployments]


@router.post("", response_model=DeploymentOut, status_code=status.HTTP_201_CREATED)
def create_deployment(
    payload: CreateDeploymentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    """Creates a `draft` deployment record only — no provider call yet.
    The website doesn't need to be finished generating yet either (a
    deployment can be planned ahead of time); readiness (status ==
    completed, has real pages) is checked at actual deploy time (POST
    /{id}/deploy) instead, matching the "Create -> Validate -> Deploy"
    flow rather than blocking record creation on it."""
    website = _get_owned_website(db, user, payload.website_id)

    deployment = Deployment(
        user_id=user.id,
        project_id=website.project_id,
        website_id=website.id,
        name=(payload.name or website.name)[:255],
        environment=DeploymentEnvironment(payload.environment),
        status=DeploymentStatus.draft,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    deployment.website = website
    return _to_deployment_out(deployment)


@router.get("/{deployment_id}", response_model=DeploymentOut)
def get_deployment(deployment_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _to_deployment_out(_get_owned_deployment(db, user, deployment_id))


@router.patch("/{deployment_id}", response_model=DeploymentOut)
def update_deployment(
    deployment_id: uuid.UUID,
    payload: UpdateDeploymentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    deployment = _get_owned_deployment(db, user, deployment_id)
    if deployment.status == DeploymentStatus.deploying:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This deployment is currently deploying and cannot be edited."
        )
    if payload.name is not None:
        deployment.name = payload.name
    if payload.environment is not None:
        deployment.environment = DeploymentEnvironment(payload.environment)
    db.commit()
    db.refresh(deployment)
    return _to_deployment_out(deployment)


@router.delete("/{deployment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deployment(
    deployment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    """Deletes only this deployment record (and its own downloadable
    archive, if any) — never touches the source website's pages/storage."""
    deployment = _get_owned_deployment(db, user, deployment_id)
    if deployment.storage_ref:
        get_storage_provider().delete(deployment.storage_ref)
    db.delete(deployment)
    db.commit()


@router.post("/{deployment_id}/deploy", response_model=DeploymentOut)
def deploy(
    deployment_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    """Also used for redeploy — any non-`deploying` status can trigger
    this again. Synchronous, matching the exact precedent of Website
    Studio's own POST /websites/{id}/deploy: LocalDeploymentProvider's
    deploy() is a fast, non-blocking zip build (not a slow external AI
    call), so this doesn't need the async background-task pattern
    Website *generation* needed."""
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)

    deployment = _get_owned_deployment(db, user, deployment_id)
    if deployment.status == DeploymentStatus.deploying:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This deployment is already in progress.")

    website = deployment.website
    if website.status != WebsiteStatus.completed or not website.pages:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="The source website has no generated pages to deploy yet."
        )

    storage_provider = get_storage_provider()
    files: dict[str, bytes] = {}
    for page in website.pages:
        try:
            files[page["path"]] = storage_provider.read(page["storage_ref"])
        except FileNotFoundError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A generated page no longer exists.")

    deployment.status = DeploymentStatus.deploying
    deployment.error = None
    db.commit()

    deployment_provider = get_deployment_provider()
    try:
        result = deployment_provider.deploy(deployment.name, files, str(user.id))
    except GenerationProviderError as exc:
        deployment.status = DeploymentStatus.failed
        deployment.error = f"Deployment failed: {exc}"
        db.commit()
        db.refresh(deployment)
        return _to_deployment_out(deployment)

    deployment.status = DeploymentStatus.active
    deployment.provider = result.provider
    deployment.storage_ref = result.storage_ref
    deployment.live_url = result.live_url
    deployment.deployed_at = utcnow()
    db.add(
        HistoryEntry(
            user_id=user.id,
            project_id=deployment.project_id,
            type=HistoryEntryType.deployment,
            status=HistoryEntryStatus.completed,
            title=f"Deployed: {deployment.name}",
            completed_at=utcnow(),
        )
    )
    db.commit()
    db.refresh(deployment)
    return _to_deployment_out(deployment)


@router.get("/{deployment_id}/download")
def download_deployment(
    deployment_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    deployment = _get_owned_deployment(db, user, deployment_id)
    if not deployment.storage_ref:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This deployment has no downloadable archive.")

    storage_provider = get_storage_provider()
    try:
        data = storage_provider.read(deployment.storage_ref)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment archive no longer exists.")

    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in deployment.name).strip() or "deployment"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.zip"'},
    )


@router.post("/{deployment_id}/stop", response_model=DeploymentOut)
def stop(
    deployment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    """Marks the deployment inactive. Honest about what this means for
    the local provider: there is no running server process to actually
    stop (LocalDeploymentProvider produces a static downloadable
    archive), so this is a real, persisted status transition — not a
    fabricated infrastructure action — and the existing archive/live_url
    are left in place so the deployment can still be redeployed later."""
    deployment = _get_owned_deployment(db, user, deployment_id)
    if deployment.status != DeploymentStatus.active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only an active deployment can be stopped.")
    deployment.status = DeploymentStatus.stopped
    db.commit()
    db.refresh(deployment)
    return _to_deployment_out(deployment)
