from app.core.config import get_settings
from app.jobs.in_process_queue import InProcessJobQueue
from app.jobs.queue import JobQueue
from app.jobs.rq_queue import RQJobQueue
from app.jobs.worker import run_job

_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """A process-wide singleton — InProcessJobQueue tracks running asyncio
    tasks, so a fresh instance per call would lose track of in-flight
    work. RQJobQueue is stateless (just publishes to Redis) and wouldn't
    strictly need this, but is cached the same way for consistency."""
    global _queue
    if _queue is None:
        settings = get_settings()
        if settings.job_queue == "in_process":
            _queue = InProcessJobQueue(worker=run_job, max_concurrent=settings.job_queue_max_workers)
        elif settings.job_queue == "rq":
            _queue = RQJobQueue(settings.redis_url, settings.rq_queue_name)
        else:
            raise ValueError(f"Unknown JOB_QUEUE '{settings.job_queue}'.")
    return _queue
