"""Tests for the RQ-backed persistent JobQueue (JOB_QUEUE=rq — see
app/jobs/rq_queue.py, app/jobs/rq_worker.py). Requires a real, reachable
local Redis instance (matching how the rest of this test suite already
requires a real local Postgres); skipped entirely when one isn't
available so JOB_QUEUE's default (in_process, tested elsewhere) stays
the only requirement for running the suite in an environment with no
Redis installed.
"""
import uuid

import pytest

try:
    import redis as redis_lib
except ImportError:  # pragma: no cover - redis is a hard requirement now, but stay defensive
    redis_lib = None

from app.jobs.rq_queue import RQJobQueue
from app.jobs.rq_worker import run_job_sync

_TEST_REDIS_URL = "redis://localhost:6379/15"  # dedicated DB index, never the dev-default db 0
_TEST_QUEUE_NAME = "test_generation_jobs"


def _redis_available() -> bool:
    if redis_lib is None:
        return False
    try:
        client = redis_lib.from_url(_TEST_REDIS_URL, socket_connect_timeout=1)
        client.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_available(), reason="Redis is not reachable in this environment")


@pytest.fixture
def rq_queue():
    queue = RQJobQueue(_TEST_REDIS_URL, _TEST_QUEUE_NAME)
    queue._queue.empty()  # start each test from a clean queue
    yield queue
    queue._queue.empty()


class TestRQJobQueue:
    def test_submit_enqueues_the_job_with_correct_function_and_args(self, rq_queue):
        job_id = uuid.uuid4()
        rq_queue.submit(job_id)

        assert rq_queue._queue.count == 1
        enqueued = rq_queue._queue.jobs[0]
        assert enqueued.func_name.endswith("run_job_sync")
        assert enqueued.args == (job_id,)

    def test_multiple_submissions_are_independently_queued(self, rq_queue):
        ids = [uuid.uuid4() for _ in range(3)]
        for job_id in ids:
            rq_queue.submit(job_id)

        assert rq_queue._queue.count == 3
        queued_args = {job.args[0] for job in rq_queue._queue.jobs}
        assert queued_args == set(ids)


class TestRunJobSync:
    def test_wraps_the_async_worker_in_its_own_event_loop(self, monkeypatch):
        captured = {}

        async def fake_run_job(job_id):
            captured["job_id"] = job_id

        monkeypatch.setattr("app.jobs.rq_worker.run_job", fake_run_job)

        job_id = uuid.uuid4()
        run_job_sync(job_id)

        assert captured["job_id"] == job_id


class TestJobQueueFactorySelectsRQ:
    def test_factory_builds_an_rq_job_queue_when_configured(self, monkeypatch):
        import app.jobs.factory as factory_module
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "job_queue", "rq")
        monkeypatch.setattr(settings, "redis_url", _TEST_REDIS_URL)
        monkeypatch.setattr(settings, "rq_queue_name", _TEST_QUEUE_NAME)
        monkeypatch.setattr(factory_module, "_queue", None)

        try:
            queue = factory_module.get_job_queue()
            assert isinstance(queue, RQJobQueue)
        finally:
            monkeypatch.setattr(factory_module, "_queue", None)
