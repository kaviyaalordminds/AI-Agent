import uuid

from redis import Redis
from rq import Queue

from app.jobs.queue import JobQueue


class RQJobQueue(JobQueue):
    """Persistent-broker JobQueue backed by Redis + RQ, for true multi-
    worker production scaling: unlike InProcessJobQueue, a submitted job
    lives in Redis (not this process's memory), so it survives an app
    server restart or crash, and any number of `python -m
    app.jobs.rq_worker` processes — potentially on separate machines —
    can pull from the same queue and share the load. Selected via
    JOB_QUEUE=rq (see app/core/config.py). This class only enqueues; it
    never runs a job itself, matching the JobQueue contract exactly the
    same way InProcessJobQueue does for local development."""

    def __init__(self, redis_url: str, queue_name: str) -> None:
        self._queue = Queue(queue_name, connection=Redis.from_url(redis_url))

    def submit(self, job_id: uuid.UUID) -> None:
        from app.jobs.rq_worker import run_job_sync

        self._queue.enqueue(run_job_sync, job_id)
