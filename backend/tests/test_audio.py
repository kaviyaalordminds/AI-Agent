"""Tests for the new Audio Generation / Transcription / Cloning features:
POST /api/jobs/audio (extended with voice_profile_id), POST
/api/generation/audio/transcribe, and POST/GET/DELETE
/api/generation/audio/voices. Reuses the existing job-queue and
auth_client/isolation patterns already established for image/video.
"""
import base64
import re

import pytest

from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import (
    GenerationProviderNotConfiguredError,
    GenerationProviderQuotaExceededError,
)
from app.integrations.generation.transcription.base import TranscriptionProvider, TranscriptionResult, TranscriptionSegment
from app.integrations.generation.voice.base import ClonedVoiceProfile, VoiceProvider, VoiceSynthesisResult
from app.models.voice_profile import VoiceProfile


def _poll_until_terminal(client, url, timeout=5.0):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(url)
        job = resp.json()
        if job["status"] in ("completed", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"Job at {url} did not reach a terminal status within {timeout}s")


def _signup_second_user(client, email_outbox, email="second-audio@example.com"):
    password = "Str0ng!Passw0rd"
    client.post(
        "/api/auth/signup",
        json={
            "full_name": "Second User",
            "email": email,
            "password": password,
            "confirm_password": password,
            "accept_terms": True,
        },
    )
    token = re.search(r"token=([A-Za-z0-9_\-]+)", email_outbox[-1].text_body).group(1)
    client.post("/api/auth/verify-email", json={"token": token})
    login_resp = client.post("/api/auth/login", json={"email": email, "password": password})
    return login_resp.cookies["aiagent_csrf"]


class _FakeTranscriptionProvider(TranscriptionProvider):
    def __init__(self, fail_with: Exception | None = None):
        self._fail_with = fail_with

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(available=True, provider="fake-openai", mode="production", reason="configured")

    async def transcribe(self, audio_data: bytes, language: str | None = None) -> TranscriptionResult:
        if self._fail_with is not None:
            raise self._fail_with
        return TranscriptionResult(
            text="hello from the fake transcript",
            language="english",
            segments=[TranscriptionSegment(start_seconds=0.0, end_seconds=1.5, text="hello from the fake transcript")],
        )


class _FakeVoiceProvider(VoiceProvider):
    def __init__(self, fail_with: Exception | None = None):
        self._fail_with = fail_with
        self.deleted_refs: list[str] = []

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(available=True, provider="fake-elevenlabs", mode="production", reason="configured")

    async def clone_voice(self, sample_audio: bytes, consent_confirmed: bool, name: str = "Cloned voice") -> ClonedVoiceProfile:
        if not consent_confirmed:
            raise ValueError("Voice cloning requires explicit confirmation that you have permission to use this voice.")
        if self._fail_with is not None:
            raise self._fail_with
        return ClonedVoiceProfile(provider_ref="fake-provider-ref-123")

    async def synthesize_with_voice(self, text: str, profile: ClonedVoiceProfile) -> VoiceSynthesisResult:
        if self._fail_with is not None:
            raise self._fail_with
        return VoiceSynthesisResult(data=b"fake-cloned-voice-mp3-bytes", format="mp3", content_type="audio/mpeg")

    async def delete_voice(self, profile: ClonedVoiceProfile) -> None:
        if self._fail_with is not None:
            raise self._fail_with
        self.deleted_refs.append(profile.provider_ref)


_SAMPLE_AUDIO_B64 = base64.b64encode(b"fake audio bytes for testing").decode()


class TestAudioJobWithVoiceProfile:
    def test_nonexistent_voice_profile_returns_404(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/jobs/audio",
            json={"text": "hello", "voice_profile_id": "00000000-0000-0000-0000-000000000000"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 404

    def test_another_users_voice_profile_returns_404(self, auth_client, client, email_outbox, db_session):
        owner_client, owner_csrf = auth_client
        owner_client.post(
            "/api/generation/audio/voices",
            json={"name": "Owner Voice", "sample_audio_base64": _SAMPLE_AUDIO_B64, "consent_confirmed": True},
            headers={"X-CSRF-Token": owner_csrf},
        )
        # Provider not configured in test env, so the clone above fails —
        # seed a real VoiceProfile row directly instead, which is what
        # this test actually needs to exist for the isolation check.
        from app.models.user import User

        owner = db_session.query(User).filter(User.email == "owner@example.com").first()
        profile = VoiceProfile(user_id=owner.id, name="Owner Voice", provider="fake", provider_ref="ref-1")
        db_session.add(profile)
        db_session.commit()
        db_session.refresh(profile)

        second_csrf = _signup_second_user(client, email_outbox)
        resp = client.post(
            "/api/jobs/audio",
            json={"text": "hello", "voice_profile_id": str(profile.id)},
            headers={"X-CSRF-Token": second_csrf},
        )
        assert resp.status_code == 404

    def test_valid_voice_profile_synthesizes_via_voice_provider(self, auth_client, db_session, monkeypatch):
        client, csrf = auth_client
        from app.models.user import User

        owner = db_session.query(User).filter(User.email == "owner@example.com").first()
        profile = VoiceProfile(user_id=owner.id, name="My Voice", provider="fake", provider_ref="ref-1")
        db_session.add(profile)
        db_session.commit()
        db_session.refresh(profile)

        import app.jobs.worker as worker_module

        fake = _FakeVoiceProvider()
        monkeypatch.setattr(worker_module, "get_voice_provider", lambda: fake)

        resp = client.post(
            "/api/jobs/audio",
            json={"text": "hello", "voice_profile_id": str(profile.id)},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 202
        job = _poll_until_terminal(client, f"/api/jobs/{resp.json()['id']}")
        assert job["status"] == "completed"
        assert job["output_metadata"]["content_type"] == "audio/mpeg"


class TestAudioTranscriptionEndpoint:
    def test_requires_authentication(self, client):
        resp = client.post("/api/generation/audio/transcribe", json={"audio_base64": _SAMPLE_AUDIO_B64})
        assert resp.status_code == 401

    def test_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post("/api/generation/audio/transcribe", json={"audio_base64": _SAMPLE_AUDIO_B64})
        assert resp.status_code == 403

    def test_invalid_base64_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/generation/audio/transcribe",
            json={"audio_base64": "not-valid-base64!!"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422

    def test_honestly_fails_when_no_provider_configured(self, auth_client):
        """Default test config has TRANSCRIPTION_PROVIDER=local with no
        Whisper backend installed in this sandbox — the job must land on
        `failed` with a real reason, never `completed` with fabricated
        text."""
        client, csrf = auth_client
        resp = client.post(
            "/api/generation/audio/transcribe", json={"audio_base64": _SAMPLE_AUDIO_B64}, headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 202
        job = _poll_until_terminal(client, f"/api/generation/audio/transcribe/{resp.json()['id']}")
        assert job["status"] == "failed"
        assert job["error_type"] == "not_configured"

    def test_successful_transcription_with_configured_provider(self, auth_client, monkeypatch):
        client, csrf = auth_client
        import app.jobs.worker as worker_module

        monkeypatch.setattr(worker_module, "get_transcription_provider", lambda: _FakeTranscriptionProvider())

        resp = client.post(
            "/api/generation/audio/transcribe", json={"audio_base64": _SAMPLE_AUDIO_B64}, headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 202
        job = _poll_until_terminal(client, f"/api/generation/audio/transcribe/{resp.json()['id']}")
        assert job["status"] == "completed"
        assert job["output_metadata"]["text"] == "hello from the fake transcript"
        assert job["output_metadata"]["language"] == "english"
        assert len(job["output_metadata"]["segments"]) == 1

    def test_quota_exceeded_is_recorded_with_structured_error_type(self, auth_client, monkeypatch):
        client, csrf = auth_client
        import app.jobs.worker as worker_module

        fake = _FakeTranscriptionProvider(fail_with=GenerationProviderQuotaExceededError("429 quota exceeded"))
        monkeypatch.setattr(worker_module, "get_transcription_provider", lambda: fake)

        resp = client.post(
            "/api/generation/audio/transcribe", json={"audio_base64": _SAMPLE_AUDIO_B64}, headers={"X-CSRF-Token": csrf}
        )
        job = _poll_until_terminal(client, f"/api/generation/audio/transcribe/{resp.json()['id']}")
        assert job["status"] == "failed"
        assert job["error_type"] == "quota_exceeded"

    def test_video_job_id_not_visible_via_transcription_route(self, auth_client):
        client, csrf = auth_client
        video_resp = client.post("/api/generation/video", json={"prompt": "a drone shot"}, headers={"X-CSRF-Token": csrf})
        video_job_id = video_resp.json()["id"]
        assert client.get(f"/api/generation/audio/transcribe/{video_job_id}").status_code == 404

    def test_isolated_between_users(self, auth_client, client, email_outbox, monkeypatch):
        import app.jobs.worker as worker_module

        monkeypatch.setattr(worker_module, "get_transcription_provider", lambda: _FakeTranscriptionProvider())
        owner_client, owner_csrf = auth_client
        resp = owner_client.post(
            "/api/generation/audio/transcribe", json={"audio_base64": _SAMPLE_AUDIO_B64}, headers={"X-CSRF-Token": owner_csrf}
        )
        job_id = resp.json()["id"]
        _poll_until_terminal(owner_client, f"/api/generation/audio/transcribe/{job_id}")

        _signup_second_user(client, email_outbox)
        assert client.get(f"/api/generation/audio/transcribe/{job_id}").status_code == 404


class TestVoiceCloningEndpoints:
    def test_create_requires_authentication(self, client):
        resp = client.post(
            "/api/generation/audio/voices",
            json={"name": "V", "sample_audio_base64": _SAMPLE_AUDIO_B64, "consent_confirmed": True},
        )
        assert resp.status_code == 401

    def test_create_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post(
            "/api/generation/audio/voices",
            json={"name": "V", "sample_audio_base64": _SAMPLE_AUDIO_B64, "consent_confirmed": True},
        )
        assert resp.status_code == 403

    def test_create_without_consent_returns_422(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/generation/audio/voices",
            json={"name": "V", "sample_audio_base64": _SAMPLE_AUDIO_B64, "consent_confirmed": False},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422

    def test_create_with_unconfigured_provider_returns_502_not_a_crash(self, auth_client):
        """Default test config has VOICE_PROVIDER=local with no local
        cloning backend — must be a clean 502, never a raw 500."""
        client, csrf = auth_client
        resp = client.post(
            "/api/generation/audio/voices",
            json={"name": "V", "sample_audio_base64": _SAMPLE_AUDIO_B64, "consent_confirmed": True},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 502
        assert "detail" in resp.json()

    def test_create_success_never_exposes_provider_ref(self, auth_client, monkeypatch):
        client, csrf = auth_client
        import app.api.generation.router as generation_router_module

        monkeypatch.setattr(generation_router_module, "get_voice_provider", lambda: _FakeVoiceProvider())

        resp = client.post(
            "/api/generation/audio/voices",
            json={"name": "My Voice", "sample_audio_base64": _SAMPLE_AUDIO_B64, "consent_confirmed": True},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "My Voice"
        assert "provider_ref" not in body
        assert "fake-provider-ref-123" not in resp.text

    def test_create_is_logged_to_history(self, auth_client, monkeypatch):
        client, csrf = auth_client
        import app.api.generation.router as generation_router_module

        monkeypatch.setattr(generation_router_module, "get_voice_provider", lambda: _FakeVoiceProvider())
        client.post(
            "/api/generation/audio/voices",
            json={"name": "My Voice", "sample_audio_base64": _SAMPLE_AUDIO_B64, "consent_confirmed": True},
            headers={"X-CSRF-Token": csrf},
        )
        history = client.get("/api/history?type=audio").json()["items"]
        assert any("My Voice" in item["title"] for item in history)

    def test_list_requires_authentication(self, client):
        assert client.get("/api/generation/audio/voices").status_code == 401

    def test_list_is_isolated_between_users(self, auth_client, client, email_outbox, db_session):
        from app.models.user import User

        owner_client, _owner_csrf = auth_client
        owner = db_session.query(User).filter(User.email == "owner@example.com").first()
        db_session.add(VoiceProfile(user_id=owner.id, name="Owner Voice", provider="fake", provider_ref="ref-1"))
        db_session.commit()

        assert len(owner_client.get("/api/generation/audio/voices").json()) == 1

        _signup_second_user(client, email_outbox)
        assert client.get("/api/generation/audio/voices").json() == []

    def test_delete_nonexistent_returns_404(self, auth_client):
        client, csrf = auth_client
        resp = client.delete(
            "/api/generation/audio/voices/00000000-0000-0000-0000-000000000000", headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 404

    def test_delete_requires_csrf(self, auth_client, db_session):
        from app.models.user import User

        client, _csrf = auth_client
        owner = db_session.query(User).filter(User.email == "owner@example.com").first()
        profile = VoiceProfile(user_id=owner.id, name="Owner Voice", provider="fake", provider_ref="ref-1")
        db_session.add(profile)
        db_session.commit()
        db_session.refresh(profile)

        resp = client.delete(f"/api/generation/audio/voices/{profile.id}")
        assert resp.status_code == 403

    def test_delete_another_users_voice_returns_404(self, auth_client, client, email_outbox, db_session):
        from app.models.user import User

        owner_client, _owner_csrf = auth_client
        owner = db_session.query(User).filter(User.email == "owner@example.com").first()
        profile = VoiceProfile(user_id=owner.id, name="Owner Voice", provider="fake", provider_ref="ref-1")
        db_session.add(profile)
        db_session.commit()
        db_session.refresh(profile)

        second_csrf = _signup_second_user(client, email_outbox)
        resp = client.delete(f"/api/generation/audio/voices/{profile.id}", headers={"X-CSRF-Token": second_csrf})
        assert resp.status_code == 404

        # Never deleted — still exists for the owner.
        assert db_session.query(VoiceProfile).filter(VoiceProfile.id == profile.id).first() is not None

    def test_delete_success_calls_provider_and_removes_row(self, auth_client, db_session, monkeypatch):
        from app.models.user import User

        client, csrf = auth_client
        owner = db_session.query(User).filter(User.email == "owner@example.com").first()
        profile = VoiceProfile(user_id=owner.id, name="Owner Voice", provider="fake", provider_ref="ref-1")
        db_session.add(profile)
        db_session.commit()
        db_session.refresh(profile)
        profile_id = profile.id

        import app.api.generation.router as generation_router_module

        fake = _FakeVoiceProvider()
        monkeypatch.setattr(generation_router_module, "get_voice_provider", lambda: fake)

        resp = client.delete(f"/api/generation/audio/voices/{profile_id}", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 204
        assert fake.deleted_refs == ["ref-1"]
        assert db_session.query(VoiceProfile).filter(VoiceProfile.id == profile_id).first() is None
