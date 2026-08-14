import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.integrations.generation.audio.factory import get_audio_provider
from app.integrations.storage.factory import get_storage_provider
from app.jobs.factory import get_job_queue
from app.models.generation_job import GenerationJob, JobStatus, JobType
from app.models.project import Project
from app.models.user import User
from app.schemas.job import CreateAudioJobRequest, JobOut
from app.security.rate_limit import enforce_rate_limit
from app.security.sessions import get_current_user, require_csrf

router = APIRouter(prefix="/jobs", tags=["jobs"])

_DOWNLOAD_CONTENT_TYPES = {
    JobType.audio: "audio",
    JobType.image: "image",
    JobType.video: "video",
}


def _get_owned_job(db: Session, user: User, job_id: uuid.UUID) -> GenerationJob:
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id, GenerationJob.user_id == user.id).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job


def _enforce_concurrency_limit(db: Session, user: User) -> None:
    settings = get_settings()
    active_count = (
        db.query(GenerationJob)
        .filter(
            GenerationJob.user_id == user.id,
            GenerationJob.status.in_([JobStatus.queued, JobStatus.processing]),
        )
        .count()
    )
    if active_count >= settings.generation_max_concurrent_jobs_per_user:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"You already have {active_count} generation job(s) in progress "
                f"(limit: {settings.generation_max_concurrent_jobs_per_user}). "
                "Wait for one to finish before starting another."
            ),
        )


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
    return _get_owned_job(db, user, job_id)


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
    _enforce_concurrency_limit(db, user)

    project = None
    if payload.project_id is not None:
        project = db.query(Project).filter(Project.id == payload.project_id, Project.user_id == user.id).first()
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    job = GenerationJob(
        user_id=user.id,
        project_id=project.id if project else None,
        type=JobType.audio,
        provider=get_audio_provider().capability().provider,
        status=JobStatus.queued,
        input_metadata={
            "text": payload.text,
            "voice": payload.voice,
            "language": payload.language,
            "speed": payload.speed,
            "format": payload.format,
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        get_job_queue().submit(job.id)
    except Exception as exc:
        # The job row is already committed — if scheduling it fails, it
        # must not be left stuck in "queued" forever with no worker ever
        # picking it up.
        job.status = JobStatus.failed
        job.error = f"Could not schedule this job for processing: {exc}"
        db.commit()
        db.refresh(job)

    return job


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    job = _get_owned_job(db, user, job_id)
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
    job = _get_owned_job(db, user, job_id)
    if job.status != JobStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is {job.status.value}, not completed — nothing to download yet.",
        )
    storage_ref = job.output_metadata.get("storage_ref")
    if not storage_ref:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This job has no downloadable output.")

    storage_provider = get_storage_provider()
    try:
        data = storage_provider.read(storage_ref)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated file no longer exists.")

    content_type = job.output_metadata.get("content_type", "application/octet-stream")
    extension = storage_ref.rsplit(".", 1)[-1] if "." in storage_ref else "bin"
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{job.type.value}-{job.id}.{extension}"'},
    )
