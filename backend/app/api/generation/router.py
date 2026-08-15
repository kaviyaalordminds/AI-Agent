"""Media-generation-specific endpoints (`POST /api/generation/image`,
`POST /api/generation/video`, ...) requested by the product spec, on top
of the existing generic GenerationJob infrastructure. All job creation,
ownership lookup, and download logic is shared with `/api/jobs/*` via
`app/jobs/service.py` — nothing here duplicates that behavior, this
module only adds prompt/provider-specific request shaping (image
width/height, optional video reference image) and type-scoped routes.

Frontend never talks to a vendor API directly: it calls these backend
routes, which resolve a provider through
get_image_provider()/get_video_provider() (env-configured, never
hard-coded — image is OpenAI, video is Gemini/Veo, see
app/core/config.py) and hand off to the GenerationJob queue. Vendor API
keys never leave the backend process.
"""
import base64
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.documents.structured import generate_structured_document
from app.documents.structured_render import render_pptx, render_structured_docx, render_xlsx
from app.integrations.generation.image.factory import get_image_provider
from app.integrations.generation.video.factory import get_video_provider
from app.integrations.storage.factory import get_storage_provider
from app.jobs.service import (
    build_download_response,
    create_and_submit_job,
    enforce_concurrency_limit,
    get_owned_job,
    resolve_owned_project,
)
from app.models.document import DocumentFormat
from app.models.generation_job import GenerationJob, JobType
from app.models.user import User
from app.schemas.document import DocumentOut
from app.schemas.generation import (
    CreateImageJobRequest,
    CreateVideoJobRequest,
    ExcelDocumentRequest,
    PptDocumentRequest,
    WordDocumentRequest,
)
from app.schemas.job import JobOut
from app.security.rate_limit import enforce_rate_limit
from app.security.sessions import get_current_user, require_csrf

logger = logging.getLogger("app.api.generation")

router = APIRouter(prefix="/generation", tags=["generation"])


def _to_document_out(document) -> DocumentOut:
    out = DocumentOut.model_validate(document)
    out.project_name = document.project.name if document.project else None
    return out


def _ensure_type(job: GenerationJob, expected_type: JobType) -> GenerationJob:
    if job.type != expected_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job


@router.post("/image", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_image_generation(
    payload: CreateImageJobRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)
    enforce_concurrency_limit(db, user)
    project = resolve_owned_project(db, user, payload.project_id)

    provider_name = get_image_provider().capability().provider
    logger.info(
        "incoming image generation request: user=%s project=%s provider=%s size=%sx%s",
        user.id, project.id if project else None, provider_name, payload.width, payload.height,
    )
    job = create_and_submit_job(
        db,
        user,
        project,
        JobType.image,
        provider_name,
        {"prompt": payload.prompt, "width": payload.width, "height": payload.height},
    )
    logger.info("image generation job created: job_id=%s status=%s", job.id, job.status.value)
    return job


@router.get("/image/{job_id}", response_model=JobOut)
def get_image_generation(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _ensure_type(get_owned_job(db, user, job_id), JobType.image)


@router.get("/image/{job_id}/download")
def download_image_generation(
    job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = _ensure_type(get_owned_job(db, user, job_id), JobType.image)
    return build_download_response(job)


@router.post("/video", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_video_generation(
    payload: CreateVideoJobRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)
    enforce_concurrency_limit(db, user)
    project = resolve_owned_project(db, user, payload.project_id)

    input_metadata: dict = {"prompt": payload.prompt, "duration_seconds": payload.duration_seconds}
    if payload.reference_image_base64:
        image_bytes = base64.b64decode(payload.reference_image_base64)
        stored = get_storage_provider().write(
            "video_reference_images", str(user.id), f"{uuid.uuid4()}.png", image_bytes
        )
        input_metadata["reference_image_ref"] = stored.ref

    provider_name = get_video_provider().capability().provider
    logger.info(
        "incoming video generation request: user=%s project=%s provider=%s duration=%s has_reference_image=%s",
        user.id, project.id if project else None, provider_name, payload.duration_seconds,
        bool(payload.reference_image_base64),
    )
    job = create_and_submit_job(
        db,
        user,
        project,
        JobType.video,
        provider_name,
        input_metadata,
    )
    logger.info("video generation job created: job_id=%s status=%s", job.id, job.status.value)
    return job


@router.get("/video/{job_id}", response_model=JobOut)
def get_video_generation(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _ensure_type(get_owned_job(db, user, job_id), JobType.video)


@router.get("/video/{job_id}/download")
def download_video_generation(
    job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = _ensure_type(get_owned_job(db, user, job_id), JobType.video)
    return build_download_response(job)


# --- Word / PowerPoint / Excel: no AI provider required, so these run
# synchronously (like the existing /api/documents flow) rather than
# through the GenerationJob queue — a local library call completes in
# milliseconds, there is nothing to poll. ---


@router.post("/document/word", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_word_document(
    payload: WordDocumentRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)
    project = resolve_owned_project(db, user, payload.project_id)

    document = generate_structured_document(
        db,
        user,
        project,
        get_storage_provider(),
        payload.title,
        DocumentFormat.docx,
        "docx",
        "word",
        lambda: render_structured_docx(payload),
    )
    return _to_document_out(document)


@router.post("/document/ppt", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_ppt_document(
    payload: PptDocumentRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)
    project = resolve_owned_project(db, user, payload.project_id)

    document = generate_structured_document(
        db,
        user,
        project,
        get_storage_provider(),
        payload.title,
        DocumentFormat.pptx,
        "pptx",
        "presentation",
        lambda: render_pptx(payload),
    )
    return _to_document_out(document)


@router.post("/document/excel", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_excel_document(
    payload: ExcelDocumentRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)
    project = resolve_owned_project(db, user, payload.project_id)

    document = generate_structured_document(
        db,
        user,
        project,
        get_storage_provider(),
        payload.title,
        DocumentFormat.xlsx,
        "xlsx",
        "spreadsheet",
        lambda: render_xlsx(payload),
    )
    return _to_document_out(document)
