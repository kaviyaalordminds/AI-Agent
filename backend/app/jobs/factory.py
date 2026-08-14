from app.core.config import get_settings
from app.jobs.in_process_queue import InProcessJobQueue
from app.jobs.queue import JobQueue
from app.jobs.worker import run_job

_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """A process-wide singleton — InProcessJobQueue tracks running asyncio
    tasks, so a fresh instance per call would lose track of in-flight
    work. A production JOB_QUEUE backed by Celery/RQ would typically be
    stateless (just publishes to a broker) and wouldn't need this."""
    global _queue
    if _queue is None:
        settings = get_settings()
        if settings.job_queue == "in_process":
            _queue = InProcessJobQueue(worker=run_job, max_concurrent=settings.job_queue_max_workers)
        else:
            raise ValueError(f"Unknown JOB_QUEUE '{settings.job_queue}'.")
    return _queue
