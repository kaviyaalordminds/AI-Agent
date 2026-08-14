import time

import pytest

from app.models.generation_job import JobStatus


def _poll_until_terminal(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        job = resp.json()
        if job["status"] in ("completed", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not reach a terminal status within {timeout}s")


class TestAudioJobEndToEnd:
    def test_requires_authentication(self, client):
        assert client.get("/api/jobs").status_code == 401
        assert client.post("/api/jobs/audio", json={"text": "hi"}).status_code == 401

    def test_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post("/api/jobs/audio", json={"text": "Hello there."})
        assert resp.status_code == 403

    def test_text_too_short_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post("/api/jobs/audio", json={"text": ""}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 422

    def test_create_audio_job_completes_via_real_local_tts(self, auth_client):
        """No mocking here — this exercises the full Frontend -> Create Job
        -> Backend -> Queue -> Worker -> Provider -> Storage -> Completed
        Job pipeline against the real espeak-ng backend."""
        client, csrf = auth_client
        resp = client.post(
            "/api/jobs/audio",
            json={"text": "This is a real end to end job queue test."},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 202
        job = resp.json()
        assert job["type"] == "audio"
        assert job["status"] in ("queued", "processing", "completed")

        completed = _poll_until_terminal(client, job["id"])
        assert completed["status"] == "completed"
        assert completed["progress"] == 100
        assert completed["output_metadata"]["content_type"] == "audio/wav"
        assert completed["output_metadata"]["size_bytes"] > 0
        assert completed["started_at"] is not None
        assert completed["completed_at"] is not None

        download = client.get(f"/api/jobs/{job['id']}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == "audio/wav"
        assert download.content[:4] == b"RIFF"

    def test_job_is_logged_to_history(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/jobs/audio", json={"text": "Log this to history please."}, headers={"X-CSRF-Token": csrf}
        )
        job_id = resp.json()["id"]
        _poll_until_terminal(client, job_id)

        history = client.get("/api/history?type=audio")
        items = history.json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "completed"

    def test_list_jobs_filters_by_type_and_status(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/jobs/audio", json={"text": "Filter test job."}, headers={"X-CSRF-Token": csrf}
        )
        job_id = resp.json()["id"]
        _poll_until_terminal(client, job_id)

        assert len(client.get("/api/jobs?type=audio").json()) == 1
        assert len(client.get("/api/jobs?type=image").json()) == 0
        assert len(client.get("/api/jobs?status=completed").json()) == 1
        assert len(client.get("/api/jobs?status=queued").json()) == 0

    def test_get_nonexistent_job_returns_404(self, auth_client):
        client, _csrf = auth_client
        assert client.get("/api/jobs/00000000-0000-0000-0000-000000000000").status_code == 404

    def test_download_before_completion_or_without_output_returns_409(self, auth_client, monkeypatch):
        """A job with no download endpoint success path (here: cancelled
        before it ever runs) must not offer a download."""
        client, csrf = auth_client
        # Force the queue to no-op so the job stays queued long enough to cancel.
        import app.jobs.service as jobs_service_module

        class _NoopQueue:
            def submit(self, job_id):
                pass

        monkeypatch.setattr(jobs_service_module, "get_job_queue", lambda: _NoopQueue())

        resp = client.post(
            "/api/jobs/audio", json={"text": "Never actually runs."}, headers={"X-CSRF-Token": csrf}
        )
        job_id = resp.json()["id"]
        assert resp.json()["status"] == "queued"

        download = client.get(f"/api/jobs/{job_id}/download")
        assert download.status_code == 409

    def test_cancel_queued_job(self, auth_client, monkeypatch):
        client, csrf = auth_client
        import app.jobs.service as jobs_service_module

        class _NoopQueue:
            def submit(self, job_id):
                pass

        monkeypatch.setattr(jobs_service_module, "get_job_queue", lambda: _NoopQueue())

        resp = client.post(
            "/api/jobs/audio", json={"text": "Cancel me before I run."}, headers={"X-CSRF-Token": csrf}
        )
        job_id = resp.json()["id"]

        cancel_resp = client.post(f"/api/jobs/{job_id}/cancel", headers={"X-CSRF-Token": csrf})
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

    def test_cancel_requires_csrf(self, auth_client, monkeypatch):
        client, _csrf = auth_client
        import app.jobs.service as jobs_service_module

        class _NoopQueue:
            def submit(self, job_id):
                pass

        monkeypatch.setattr(jobs_service_module, "get_job_queue", lambda: _NoopQueue())
        resp = client.post(
            "/api/jobs/audio", json={"text": "CSRF check."}, headers={"X-CSRF-Token": _csrf}
        )
        job_id = resp.json()["id"]

        cancel_resp = client.post(f"/api/jobs/{job_id}/cancel")
        assert cancel_resp.status_code == 403

    def test_cancel_already_completed_job_returns_409(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/jobs/audio", json={"text": "Complete then try to cancel."}, headers={"X-CSRF-Token": csrf}
        )
        job_id = resp.json()["id"]
        _poll_until_terminal(client, job_id)

        cancel_resp = client.post(f"/api/jobs/{job_id}/cancel", headers={"X-CSRF-Token": csrf})
        assert cancel_resp.status_code == 409

    def test_concurrent_job_limit_enforced(self, auth_client, monkeypatch):
        client, csrf = auth_client
        import app.jobs.service as jobs_service_module
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "generation_max_concurrent_jobs_per_user", 2)

        class _NoopQueue:
            def submit(self, job_id):
                pass  # jobs stay "queued" forever, so they count toward the limit

        monkeypatch.setattr(jobs_service_module, "get_job_queue", lambda: _NoopQueue())

        for _ in range(2):
            resp = client.post(
                "/api/jobs/audio", json={"text": "Fill up the concurrency limit."}, headers={"X-CSRF-Token": csrf}
            )
            assert resp.status_code == 202

        over_limit = client.post(
            "/api/jobs/audio", json={"text": "This one should be rejected."}, headers={"X-CSRF-Token": csrf}
        )
        assert over_limit.status_code == 429

    def test_jobs_are_isolated_between_users(self, auth_client, client, email_outbox):
        import re

        owner_client, owner_csrf = auth_client
        resp = owner_client.post(
            "/api/jobs/audio", json={"text": "Owner private job."}, headers={"X-CSRF-Token": owner_csrf}
        )
        job_id = resp.json()["id"]
        _poll_until_terminal(owner_client, job_id)

        second_password = "Str0ng!Passw0rd"
        client.post(
            "/api/auth/signup",
            json={
                "full_name": "Second User",
                "email": "second-jobs@example.com",
                "password": second_password,
                "confirm_password": second_password,
                "accept_terms": True,
            },
        )
        token = re.search(r"token=([A-Za-z0-9_\-]+)", email_outbox[-1].text_body).group(1)
        client.post("/api/auth/verify-email", json={"token": token})
        client.post("/api/auth/login", json={"email": "second-jobs@example.com", "password": second_password})

        assert client.get("/api/jobs").json() == []
        assert client.get(f"/api/jobs/{job_id}").status_code == 404
        assert client.get(f"/api/jobs/{job_id}/download").status_code == 404

    def test_project_association(self, auth_client):
        client, csrf = auth_client
        project = client.post(
            "/api/projects", json={"name": "Audio Project"}, headers={"X-CSRF-Token": csrf}
        ).json()

        resp = client.post(
            "/api/jobs/audio",
            json={"text": "Job tied to a project.", "project_id": project["id"]},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 202
        assert resp.json()["project_id"] == project["id"]

    def test_invalid_project_id_returns_404(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/jobs/audio",
            json={"text": "Bad project.", "project_id": "00000000-0000-0000-0000-000000000000"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 404


class TestJobFailureHandling:
    def test_unavailable_provider_job_fails_honestly(self, auth_client, monkeypatch):
        """Simulates a job type whose provider is genuinely unavailable
        (like image/video/voice in this environment) by pointing the audio
        job's runner dependency at an always-unconfigured fake — the job
        must land on `failed` with a real error, never `completed` with
        fabricated output."""
        client, csrf = auth_client

        import app.jobs.worker as worker_module
        from app.integrations.capability import CapabilityStatus
        from app.integrations.generation.audio.base import AudioProvider
        from app.integrations.generation.errors import GenerationProviderNotConfiguredError

        class _AlwaysUnavailableAudio(AudioProvider):
            def capability(self):
                return CapabilityStatus(available=False, provider="fake", mode="local", reason="fake unavailable")

            async def synthesize(self, *args, **kwargs):
                raise GenerationProviderNotConfiguredError("Fake audio provider is not configured.")

        monkeypatch.setattr(worker_module, "get_audio_provider", lambda: _AlwaysUnavailableAudio())

        resp = client.post(
            "/api/jobs/audio", json={"text": "This should fail honestly."}, headers={"X-CSRF-Token": csrf}
        )
        job_id = resp.json()["id"]
        completed = _poll_until_terminal(client, job_id)
        assert completed["status"] == "failed"
        assert "not configured" in completed["error"].lower()
        assert completed["output_metadata"] == {}
