"""Media-generation-specific endpoints (`POST /api/generation/image`,
`POST /api/generation/video`, ...) requested by the product spec, on top
of the existing generic GenerationJob infrastructure. All job creation,
ownership lookup, and download logic is shared with `/api/jobs/*` via
`app/jobs/service.py` — nothing here duplicates that behavior, this
module only adds prompt/provider-specific request shaping (image
width/height, optional video reference image) and type-scoped routes.

Poster/logo/graphic-design generation (`/poster`, `/logo`, `/design`)
reuse this exact image pipeline (same provider, same job queue, same
`_run_image_job` worker) — they only add domain-specific structured
request fields (headline/brand name/design type, etc.) that get turned
into a purpose-built prompt here rather than making the caller write
the whole image prompt by hand.

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
from app.database.base import utcnow
from app.database.session import get_db
from app.documents.structured import generate_structured_document
from app.documents.structured_render import render_pptx, render_structured_docx, render_xlsx
from app.integrations.generation.errors import GenerationProviderError
from app.integrations.generation.image.factory import get_image_provider
from app.integrations.generation.transcription.factory import get_transcription_provider
from app.integrations.generation.video.factory import get_video_provider
from app.integrations.generation.voice.base import ClonedVoiceProfile
from app.integrations.generation.voice.factory import get_voice_provider
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
from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType
from app.models.user import User
from app.models.voice_profile import VoiceProfile
from app.schemas.document import DocumentOut
from app.schemas.generation import (
    CreateGraphicDesignJobRequest,
    CreateImageEnhancementJobRequest,
    CreateImageJobRequest,
    CreateLogoJobRequest,
    CreatePosterJobRequest,
    CreateTranscriptionJobRequest,
    CreateVideoJobRequest,
    ExcelDocumentRequest,
    PptDocumentRequest,
    WordDocumentRequest,
    sniff_image_format,
)
from app.schemas.job import JobOut
from app.schemas.voice import CreateVoiceCloneRequest, VoiceProfileOut
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


# --- Image Enhancement: takes an existing uploaded image and improves it
# via the same OpenAIImageProvider used by Image Generation (its
# `enhance()` method, image-to-image via OpenAI's /v1/images/edits), NOT
# a duplicate provider architecture. Follows the exact same job-queue
# pattern as plain image generation above (POST creates a queued
# GenerationJob and returns 202 immediately; app/jobs/worker.py's
# _run_image_enhancement_job does the actual provider call out of
# request scope) — the only difference is the source image is uploaded
# and stored first, and the prompt is built server-side from a small set
# of enhancement presets rather than typed by hand.
_ENHANCEMENT_PROMPTS = {
    "auto": (
        "Enhance this image: improve overall clarity, lighting, and color balance, and "
        "increase detail, while preserving the original subject and composition exactly."
    ),
    "upscale": (
        "Upscale this image, increasing resolution and detail while preserving the "
        "original subject and composition exactly."
    ),
    "denoise": (
        "Remove noise and grain from this image, smoothing artifacts while preserving "
        "genuine detail and the original subject and composition exactly."
    ),
    "color_correction": (
        "Correct the color balance, exposure, and contrast of this image for a natural, "
        "well-balanced look, preserving the original subject and composition exactly."
    ),
    "sharpen": (
        "Sharpen this image and enhance fine detail and edge definition, preserving the "
        "original subject and composition exactly."
    ),
    "restore": (
        "Restore this image: repair damage, fading, or artifacts and recover natural "
        "detail, preserving the original subject and composition exactly."
    ),
}


def _build_enhancement_prompt(enhancement_type: str, custom_prompt: str | None) -> str:
    base = _ENHANCEMENT_PROMPTS.get(enhancement_type, "")
    if custom_prompt:
        return f"{base} Additional instructions: {custom_prompt}" if base else custom_prompt
    return base


@router.post("/image/enhance", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_image_enhancement(
    payload: CreateImageEnhancementJobRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)
    enforce_concurrency_limit(db, user)
    project = resolve_owned_project(db, user, payload.project_id)

    image_bytes = base64.b64decode(payload.image_base64)
    content_type = sniff_image_format(image_bytes)  # already validated by the schema; re-derived, never trusted from the client
    extension = content_type.split("/")[-1]
    stored = get_storage_provider().write(
        "image_enhancement_uploads", str(user.id), f"{uuid.uuid4()}.{extension}", image_bytes
    )

    built_prompt = _build_enhancement_prompt(payload.enhancement_type, payload.prompt)
    provider_name = get_image_provider().capability().provider
    logger.info(
        "incoming image enhancement request: user=%s project=%s provider=%s enhancement_type=%s",
        user.id, project.id if project else None, provider_name, payload.enhancement_type,
    )
    job = create_and_submit_job(
        db,
        user,
        project,
        JobType.image_enhancement,
        provider_name,
        {
            "source_image_ref": stored.ref,
            "source_content_type": content_type,
            "prompt": built_prompt,
            "enhancement_type": payload.enhancement_type,
            "width": payload.width,
            "height": payload.height,
        },
    )
    logger.info("image enhancement job created: job_id=%s status=%s", job.id, job.status.value)
    return job


@router.get("/image/enhance/{job_id}", response_model=JobOut)
def get_image_enhancement(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _ensure_type(get_owned_job(db, user, job_id), JobType.image_enhancement)


@router.get("/image/enhance/{job_id}/download")
def download_image_enhancement(
    job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = _ensure_type(get_owned_job(db, user, job_id), JobType.image_enhancement)
    return build_download_response(job)


@router.post("/poster", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_poster_generation(
    payload: CreatePosterJobRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)
    enforce_concurrency_limit(db, user)
    project = resolve_owned_project(db, user, payload.project_id)

    built_prompt = f"Create a poster design. Prominently display the text '{payload.headline}'"
    if payload.subheading:
        built_prompt += f" with the subheading '{payload.subheading}'"
    built_prompt += (
        f". Visual style and subject: {payload.prompt}. "
        "Professional poster layout, high visual impact, legible typography."
    )

    provider_name = get_image_provider().capability().provider
    job = create_and_submit_job(
        db,
        user,
        project,
        JobType.poster,
        provider_name,
        {
            "prompt": built_prompt,
            "width": payload.width,
            "height": payload.height,
            "headline": payload.headline,
            "subheading": payload.subheading,
        },
    )
    logger.info("poster generation job created: job_id=%s status=%s", job.id, job.status.value)
    return job


@router.get("/poster/{job_id}", response_model=JobOut)
def get_poster_generation(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _ensure_type(get_owned_job(db, user, job_id), JobType.poster)


@router.get("/poster/{job_id}/download")
def download_poster_generation(
    job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = _ensure_type(get_owned_job(db, user, job_id), JobType.poster)
    return build_download_response(job)


@router.post("/logo", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_logo_generation(
    payload: CreateLogoJobRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)
    enforce_concurrency_limit(db, user)
    project = resolve_owned_project(db, user, payload.project_id)

    built_prompt = f"Design a {payload.style} logo for a brand called '{payload.brand_name}'."
    if payload.description:
        built_prompt += f" Additional concept details: {payload.description}."
    if payload.colors:
        built_prompt += f" Color palette: {payload.colors}."
    built_prompt += (
        " Clean, professional, suitable for a company brand identity, "
        "centered on a plain background, vector-style."
    )

    provider_name = get_image_provider().capability().provider
    job = create_and_submit_job(
        db,
        user,
        project,
        JobType.logo,
        provider_name,
        {
            "prompt": built_prompt,
            "width": 1024,
            "height": 1024,
            "brand_name": payload.brand_name,
            "style": payload.style,
        },
    )
    logger.info("logo generation job created: job_id=%s status=%s", job.id, job.status.value)
    return job


@router.get("/logo/{job_id}", response_model=JobOut)
def get_logo_generation(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _ensure_type(get_owned_job(db, user, job_id), JobType.logo)


@router.get("/logo/{job_id}/download")
def download_logo_generation(
    job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = _ensure_type(get_owned_job(db, user, job_id), JobType.logo)
    return build_download_response(job)


@router.post("/design", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_graphic_design_generation(
    payload: CreateGraphicDesignJobRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)
    enforce_concurrency_limit(db, user)
    project = resolve_owned_project(db, user, payload.project_id)

    design_type_label = payload.design_type.replace("_", " ")
    built_prompt = (
        f"Create a {design_type_label} graphic design. {payload.prompt} "
        "Professional, visually appealing, well-composed layout."
    )

    provider_name = get_image_provider().capability().provider
    job = create_and_submit_job(
        db,
        user,
        project,
        JobType.graphic_design,
        provider_name,
        {
            "prompt": built_prompt,
            "width": payload.width,
            "height": payload.height,
            "design_type": payload.design_type,
        },
    )
    logger.info("graphic design generation job created: job_id=%s status=%s", job.id, job.status.value)
    return job


@router.get("/design/{job_id}", response_model=JobOut)
def get_graphic_design_generation(
    job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return _ensure_type(get_owned_job(db, user, job_id), JobType.graphic_design)


@router.get("/design/{job_id}/download")
def download_graphic_design_generation(
    job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = _ensure_type(get_owned_job(db, user, job_id), JobType.graphic_design)
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


@router.post("/audio/transcribe", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_audio_transcription(
    payload: CreateTranscriptionJobRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)
    enforce_concurrency_limit(db, user)
    project = resolve_owned_project(db, user, payload.project_id)

    audio_bytes = base64.b64decode(payload.audio_base64)
    stored = get_storage_provider().write("audio_uploads", str(user.id), f"{uuid.uuid4()}.audio", audio_bytes)

    provider_name = get_transcription_provider().capability().provider
    logger.info(
        "incoming transcription request: user=%s project=%s provider=%s bytes=%d",
        user.id, project.id if project else None, provider_name, len(audio_bytes),
    )
    job = create_and_submit_job(
        db,
        user,
        project,
        JobType.transcription,
        provider_name,
        {"audio_ref": stored.ref, "language": payload.language},
    )
    logger.info("transcription job created: job_id=%s status=%s", job.id, job.status.value)
    return job


@router.get("/audio/transcribe/{job_id}", response_model=JobOut)
def get_audio_transcription(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _ensure_type(get_owned_job(db, user, job_id), JobType.transcription)


@router.post("/audio/voices", response_model=VoiceProfileOut, status_code=status.HTTP_201_CREATED)
async def create_voice_clone(
    payload: CreateVoiceCloneRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    """Synchronous, not job-queued: cloning a voice with a real vendor
    (ElevenLabs) typically completes in a few seconds, not the minutes a
    video job can take — matches the synchronous pattern the structured
    Word/PPT/Excel endpoints below already use for fast operations,
    rather than forcing every generation-shaped feature through the job
    queue whether it needs it or not."""
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)

    sample_audio = base64.b64decode(payload.sample_audio_base64)
    provider = get_voice_provider()
    provider_name = provider.capability().provider

    try:
        cloned = await provider.clone_voice(sample_audio, payload.consent_confirmed, name=payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except GenerationProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Voice cloning failed: {exc}")

    profile = VoiceProfile(user_id=user.id, name=payload.name, provider=provider_name, provider_ref=cloned.provider_ref)
    db.add(profile)
    db.commit()
    db.refresh(profile)

    db.add(
        HistoryEntry(
            user_id=user.id,
            type=HistoryEntryType.audio,
            status=HistoryEntryStatus.completed,
            title=f"Cloned voice: {payload.name}",
            completed_at=utcnow(),
        )
    )
    db.commit()

    logger.info("voice cloned: user=%s voice_profile_id=%s provider=%s", user.id, profile.id, provider_name)
    return profile


@router.get("/audio/voices", response_model=list[VoiceProfileOut])
def list_voice_clones(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(VoiceProfile)
        .filter(VoiceProfile.user_id == user.id)
        .order_by(VoiceProfile.created_at.desc())
        .all()
    )


@router.delete("/audio/voices/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice_clone(
    voice_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    profile = db.query(VoiceProfile).filter(VoiceProfile.id == voice_id, VoiceProfile.user_id == user.id).first()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")

    try:
        await get_voice_provider().delete_voice(ClonedVoiceProfile(provider_ref=profile.provider_ref))
    except GenerationProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not delete voice: {exc}")

    db.delete(profile)
    db.commit()


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
