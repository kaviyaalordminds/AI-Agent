import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

from app.jobs.queue import JobQueue

logger = logging.getLogger("app.jobs")


class InProcessJobQueue(JobQueue):
    """Local-development job queue: runs jobs as asyncio tasks in the same
    process as the web server, bounded by a semaphore so an unbounded
    burst of submissions can't starve the event loop. This is the
    "lightweight local worker" the architecture calls for — no Redis, no
    separate worker process required for local testing — while staying
    behind the same JobQueue interface a Celery/RQ-backed implementation
    would use in production, so swapping it later touches only
    app/jobs/factory.py.
    """

    def __init__(self, worker: Callable[[uuid.UUID], Awaitable[None]], max_concurrent: int) -> None:
        self._worker = worker
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._tasks: set[asyncio.Task] = set()

    def submit(self, job_id: uuid.UUID) -> None:
        task = asyncio.create_task(self._run(job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, job_id: uuid.UUID) -> None:
        async with self._semaphore:
            try:
                await self._worker(job_id)
            except Exception:
                # The worker itself already catches and records provider/
                # unexpected errors onto the job row — this is a final
                # backstop so a queue-level bug can never silently swallow
                # a job without at least being logged.
                logger.exception("InProcessJobQueue: unhandled error running job %s", job_id)
