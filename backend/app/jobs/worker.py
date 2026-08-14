"""Executes one GenerationJob end-to-end: Provider -> Storage -> job row
update. Runs outside HTTP request scope (see app/jobs/in_process_queue.py),
so it opens its own DB session — the request that created the job has
already returned a response by the time this runs.

Never lets a job vanish silently: any failure (a provider being
unconfigured, a provider call failing, or a genuinely unexpected
exception) is caught and recorded on the job row as a real, honest
`failed` status with the actual error — never left `processing` forever,
and never reported as `completed` with fabricated output.
"""
import logging
import uuid

from app.database.base import utcnow
from app.database.session import SessionLocal
from app.integrations.generation.audio.factory import get_audio_provider
from app.integrations.generation.errors import GenerationProviderError
from app.integrations.generation.image.factory import get_image_provider
from app.integrations.generation.transcription.factory import get_transcription_provider
from app.integrations.generation.video.factory import get_video_provider
from app.integrations.storage.errors import StorageError
from app.integrations.storage.factory import get_storage_provider
from app.models.generation_job import GenerationJob, JobStatus, JobType
from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType

logger = logging.getLogger("app.jobs")

_HISTORY_TYPE_FOR_JOB_TYPE = {
    JobType.audio: HistoryEntryType.audio,
    JobType.image: HistoryEntryType.image,
    JobType.video: HistoryEntryType.video,
}


async def _run_audio_job(job: GenerationJob, storage) -> dict:
    provider = get_audio_provider()
    meta = job.input_metadata
    result = await provider.synthesize(
        text=meta["text"],
        voice=meta.get("voice"),
        language=meta.get("language"),
        speed=meta.get("speed", 1.0),
        format=meta.get("format", "wav"),
    )
    stored = storage.write("generated_audio", str(job.user_id), f"{job.id}.{result.format}", result.data)
    return {"storage_ref": stored.ref, "content_type": result.content_type, "size_bytes": stored.size_bytes}


async def _run_transcription_job(job: GenerationJob, storage) -> dict:
    provider = get_transcription_provider()
    audio_bytes = storage.read(job.input_metadata["audio_ref"])
    result = await provider.transcribe(audio_bytes, language=job.input_metadata.get("language"))
    return {
        "text": result.text,
        "language": result.language,
        "segments": [
            {"start": s.start_seconds, "end": s.end_seconds, "text": s.text} for s in result.segments
        ],
    }


async def _run_image_job(job: GenerationJob, storage) -> dict:
    provider = get_image_provider()
    meta = job.input_metadata
    result = await provider.generate(meta["prompt"], width=meta.get("width", 1024), height=meta.get("height", 1024))
    stored = storage.write("generated_images", str(job.user_id), f"{job.id}.{result.format}", result.data)
    return {"storage_ref": stored.ref, "content_type": result.content_type, "size_bytes": stored.size_bytes}


async def _run_video_job(job: GenerationJob, storage) -> dict:
    provider = get_video_provider()
    meta = job.input_metadata
    reference_image = None
    if meta.get("reference_image_ref"):
        reference_image = storage.read(meta["reference_image_ref"])
    result = await provider.generate(
        meta["prompt"], duration_seconds=meta.get("duration_seconds", 4.0), reference_image=reference_image
    )
    stored = storage.write("generated_videos", str(job.user_id), f"{job.id}.{result.format}", result.data)
    return {"storage_ref": stored.ref, "content_type": result.content_type, "size_bytes": stored.size_bytes}


_RUNNERS = {
    JobType.audio: _run_audio_job,
    JobType.transcription: _run_transcription_job,
    JobType.image: _run_image_job,
    JobType.video: _run_video_job,
}


async def run_job(job_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if job is None:
            logger.warning("run_job called for missing job %s", job_id)
            return
        if job.status == JobStatus.cancelled:
            return

        job.status = JobStatus.processing
        job.started_at = utcnow()
        db.commit()

        runner = _RUNNERS.get(job.type)
        if runner is None:
            raise GenerationProviderError(f"No worker is registered for job type '{job.type.value}'.")

        storage = get_storage_provider()
        try:
            output = await runner(job, storage)
        except (GenerationProviderError, StorageError) as exc:
            job.status = JobStatus.failed
            job.error = str(exc)
            job.completed_at = utcnow()
            _log_history(db, job, HistoryEntryStatus.failed)
            db.commit()
            return
        except Exception:
            logger.exception("Unexpected error running job %s (%s)", job_id, job.type.value)
            job.status = JobStatus.failed
            job.error = "An unexpected error occurred while processing this job."
            job.completed_at = utcnow()
            _log_history(db, job, HistoryEntryStatus.failed)
            db.commit()
            return

        job.status = JobStatus.completed
        job.progress = 100
        job.output_metadata = output
        job.completed_at = utcnow()
        _log_history(db, job, HistoryEntryStatus.completed)
        db.commit()
    finally:
        db.close()


def _log_history(db, job: GenerationJob, status: HistoryEntryStatus) -> None:
    history_type = _HISTORY_TYPE_FOR_JOB_TYPE.get(job.type)
    if history_type is None:
        return
    db.add(
        HistoryEntry(
            user_id=job.user_id,
            project_id=job.project_id,
            type=history_type,
            status=status,
            title=f"{job.type.value.capitalize()} generation job",
            completed_at=utcnow() if status == HistoryEntryStatus.completed else None,
        )
    )
