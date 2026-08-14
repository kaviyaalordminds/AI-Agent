"""Shared GenerationJob create/lookup/download logic, used by both
/api/jobs/* (generic job endpoints) and /api/generation/* (the
media-generation-specific endpoints requested by the product spec) so
the two route surfaces never duplicate this behavior.
"""
import uuid

from fastapi import HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.storage.factory import get_storage_provider
from app.jobs.factory import get_job_queue
from app.models.generation_job import GenerationJob, JobStatus, JobType
from app.models.project import Project
from app.models.user import User


def get_owned_job(db: Session, user: User, job_id: uuid.UUID) -> GenerationJob:
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id, GenerationJob.user_id == user.id).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job


def enforce_concurrency_limit(db: Session, user: User) -> None:
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


def resolve_owned_project(db: Session, user: User, project_id: uuid.UUID | None) -> Project | None:
    if project_id is None:
        return None
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user.id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def create_and_submit_job(
    db: Session,
    user: User,
    project: Project | None,
    job_type: JobType,
    provider_name: str,
    input_metadata: dict,
) -> GenerationJob:
    """Persists a queued job and hands it to the job queue. If scheduling
    itself fails, the job is marked failed immediately rather than left
    stuck `queued` forever with no worker to pick it up."""
    job = GenerationJob(
        user_id=user.id,
        project_id=project.id if project else None,
        type=job_type,
        provider=provider_name,
        status=JobStatus.queued,
        input_metadata=input_metadata,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        get_job_queue().submit(job.id)
    except Exception as exc:
        job.status = JobStatus.failed
        job.error = f"Could not schedule this job for processing: {exc}"
        db.commit()
        db.refresh(job)

    return job


def build_download_response(job: GenerationJob) -> Response:
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
