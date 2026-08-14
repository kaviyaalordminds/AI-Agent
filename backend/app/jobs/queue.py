"""JobQueue abstraction.

Same provider-abstraction pattern as everywhere else in this codebase.
`submit()` takes only a job id (not a raw coroutine/closure) so this
interface stays honestly compatible with a real distributed queue later:
a Celery/RQ-backed JobQueue would serialize the id onto a broker and a
separate worker process would look the job up and run it — exactly what
InProcessJobQueue does in-process for local development. Business logic
(app/jobs/worker.py) never needs to change when the queue implementation
does.
"""
import uuid
from abc import ABC, abstractmethod


class JobQueue(ABC):
    @abstractmethod
    def submit(self, job_id: uuid.UUID) -> None:
        """Schedule the job for execution. Must not block, and must not
        raise for a healthy queue — a submission failure should itself be
        recorded as a job failure, not raised into the request handler
        that created the job.

        InProcessJobQueue's implementation schedules an asyncio task and
        therefore must be called from the event loop thread — i.e. from
        an `async def` FastAPI endpoint, not a sync `def` one (FastAPI
        runs sync endpoints in a worker thread pool with no running
        loop). A production queue backed by a real broker would not have
        this constraint."""
        raise NotImplementedError
