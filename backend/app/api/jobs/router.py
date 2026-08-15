import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.integrations.generation.audio.factory import get_audio_provider
from app.integrations.generation.voice.factory import get_voice_provider
from app.jobs.service import (
    build_download_response,
    create_and_submit_job,
    enforce_concurrency_limit,
    get_owned_job,
    resolve_owned_project,
)
from app.models.generation_job import GenerationJob, JobStatus, JobType
from app.models.user import User
from app.models.voice_profile import VoiceProfile
from app.schemas.job import CreateAudioJobRequest, JobOut
from app.security.rate_limit import enforce_rate_limit
from app.security.sessions import get_current_user, require_csrf

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(
    type: JobType | None = Query(default=None),
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    project_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(GenerationJob).filter(GenerationJob.user_id == user.id)
    if type is not None:
        query = query.filter(GenerationJob.type == type)
    if status_filter is not None:
        query = query.filter(GenerationJob.status == status_filter)
    if project_id is not None:
        query = query.filter(GenerationJob.project_id == project_id)
    jobs = query.order_by(GenerationJob.created_at.desc()).all()
    return jobs


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_owned_job(db, user, job_id)


@router.post("/audio", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_audio_job(
    payload: CreateAudioJobRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    settings = get_settings()
    enforce_rate_limit(request, "generation", settings.generation_rate_limit_max_requests)
    enforce_concurrency_limit(db, user)

    project = resolve_owned_project(db, user, payload.project_id)

    input_metadata: dict = {
        "text": payload.text,
        "voice": payload.voice,
        "language": payload.language,
        "speed": payload.speed,
        "format": payload.format,
    }
    if payload.voice_profile_id is not None:
        profile = (
            db.query(VoiceProfile)
            .filter(VoiceProfile.id == payload.voice_profile_id, VoiceProfile.user_id == user.id)
            .first()
        )
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")
        input_metadata["voice_profile_id"] = str(profile.id)
        provider_name = get_voice_provider().capability().provider
    else:
        provider_name = get_audio_provider().capability().provider

    return create_and_submit_job(db, user, project, JobType.audio, provider_name, input_metadata)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    job = get_owned_job(db, user, job_id)
    if job.status != JobStatus.queued:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is already {job.status.value} and cannot be cancelled.",
        )
    job.status = JobStatus.cancelled
    db.commit()
    db.refresh(job)
    return job


@router.get("/{job_id}/download")
def download_job_output(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = get_owned_job(db, user, job_id)
    return build_download_response(job)
