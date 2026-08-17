"""Synchronous entrypoint RQ workers can import and call — RQ has no
native asyncio support, so each job gets its own event loop here around
the real async app/jobs/worker.run_job (the same function InProcessJobQueue
calls directly). Business logic never duplicates between the two queue
implementations; only this thin adapter differs.

Run a worker process with (from the backend/ directory, once JOB_QUEUE=rq
and REDIS_URL are configured):

    python -m app.jobs.rq_worker

Any number of these can run concurrently, including on separate
machines, as long as they share REDIS_URL and this codebase.
"""
import logging
import uuid

from app.jobs.worker import run_job

logger = logging.getLogger("app.jobs")


def run_job_sync(job_id: uuid.UUID) -> None:
    import asyncio

    asyncio.run(run_job(job_id))


if __name__ == "__main__":
    from redis import Redis
    from rq import Worker

    from app.core.config import get_settings
    from app.core.logging import configure_logging

    configure_logging()
    settings = get_settings()
    connection = Redis.from_url(settings.redis_url)
    logger.info(
        "Starting RQ worker: queue=%s redis_url=%s", settings.rq_queue_name, settings.redis_url
    )
    worker = Worker([settings.rq_queue_name], connection=connection)
    worker.work()
