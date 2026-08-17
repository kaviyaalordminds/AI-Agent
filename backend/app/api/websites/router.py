import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.database.base import utcnow
from app.database.session import get_db
from app.integrations.claude.errors import ProviderNotConfiguredError
from app.integrations.claude.factory import get_claude_provider
from app.integrations.deployment.factory import get_deployment_provider
from app.integrations.generation.errors import GenerationProviderError
from app.integrations.storage.factory import get_storage_provider
from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType
from app.models.project import Project
from app.models.user import User
from app.models.website import Website, WebsiteStatus
from app.schemas.website import CreateWebsiteRequest, DeployWebsiteResponse, WebsiteOut
from app.security.rate_limit import enforce_rate_limit
from app.security.sessions import get_current_user, require_csrf
from app.websites.generator import generate_website, record_unavailable_website

router = APIRouter(prefix="/websites", tags=["websites"])


def _to_website_out(website: Website) -> WebsiteOut:
    out = WebsiteOut.model_validate(website)
    out.project_name = website.project.name if website.project else None
    return out


def _get_owned_website(db: Session, user: User, website_id: uuid.UUID) -> Website:
    website = db.query(Website).filter(Website.id == website_id, Website.user_id == user.id).first()
    if website is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found.")
    return website


@router.get("", response_model=list[WebsiteOut])
def list_websites(
    project_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Website).options(joinedload(Website.project)).filter(Website.user_id == user.id)
    if project_id is not None:
        query = query.filter(Website.project_id == project_id)
    websites = query.order_by(Website.created_at.desc()).all()
    return [_to_website_out(w) for w in websites]


@router.get("/{website_id}", response_model=WebsiteOut)
def get_website(website_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _to_website_out(_get_owned_website(db, user, website_id))


@router.post("", response_model=WebsiteOut, status_code=status.HTTP_201_CREATED)
async def create_website(
    payload: CreateWebsiteRequest,
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
        record_unavailable_website(db, user, project, payload.name, payload.prompt, payload.style, str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    storage_provider = get_storage_provider()
    website = await generate_website(
        db, user, project, claude_provider, storage_provider,
        payload.name, payload.prompt, payload.style, payload.pages,
    )
    return _to_website_out(website)


@router.get("/{website_id}/preview/{page_path}")
def preview_website_page(
    website_id: uuid.UUID, page_path: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    website = _get_owned_website(db, user, website_id)
    page = next((p for p in website.pages if p["path"] == page_path), None)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found.")

    storage_provider = get_storage_provider()
    try:
        data = storage_provider.read(page["storage_ref"])
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated page no longer exists.")
    return Response(content=data, media_type="text/html; charset=utf-8")


@router.delete("/{website_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_website(
    website_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    website = _get_owned_website(db, user, website_id)
    storage_provider = get_storage_provider()
    for page in website.pages:
        storage_provider.delete(page["storage_ref"])
    if website.deployment_storage_ref:
        storage_provider.delete(website.deployment_storage_ref)
    db.delete(website)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{website_id}/deploy", response_model=DeployWebsiteResponse)
def deploy_website(
    website_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)

    website = _get_owned_website(db, user, website_id)
    if website.status != WebsiteStatus.completed or not website.pages:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This website has no generated pages to deploy.")

    storage_provider = get_storage_provider()
    files: dict[str, bytes] = {}
    for page in website.pages:
        try:
            files[page["path"]] = storage_provider.read(page["storage_ref"])
        except FileNotFoundError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A generated page no longer exists.")

    deployment_provider = get_deployment_provider()
    try:
        result = deployment_provider.deploy(website.name, files, str(user.id))
    except GenerationProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Deployment failed: {exc}")

    website.deployment_provider = result.provider
    website.deployment_storage_ref = result.storage_ref
    website.deployment_live_url = result.live_url
    db.add(
        HistoryEntry(
            user_id=user.id,
            project_id=website.project_id,
            type=HistoryEntryType.deployment,
            status=HistoryEntryStatus.completed,
            title=f"Deployed website: {website.name}",
            completed_at=utcnow(),
        )
    )
    db.commit()

    return DeployWebsiteResponse(
        provider=result.provider, downloadable=result.storage_ref is not None, live_url=result.live_url
    )


@router.get("/{website_id}/deployment/download")
def download_website_deployment(
    website_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    website = _get_owned_website(db, user, website_id)
    if not website.deployment_storage_ref:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This website has not been deployed yet.")

    storage_provider = get_storage_provider()
    try:
        data = storage_provider.read(website.deployment_storage_ref)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment archive no longer exists.")

    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in website.name).strip() or "website"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.zip"'},
    )
