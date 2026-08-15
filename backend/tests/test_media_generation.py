"""Tests for the AI Media + Document Generation phase: /api/generation/image,
/api/generation/video (image/video generation jobs, backed by
OpenAIImageProvider/GeminiVideoProvider once configured, exercised here via
fakes so no real network call is made), and /api/generation/document/
{word,ppt,excel} (structured, non-AI document generation via
python-docx/python-pptx/openpyxl).
"""
import io
import re
import time
import zipfile

import pytest

from app.integrations.capability import CapabilityStatus
from app.integrations.generation.errors import (
    GenerationProviderNotConfiguredError,
    GenerationProviderQuotaExceededError,
    GenerationProviderRequestError,
)
from app.integrations.generation.image.base import GeneratedImage, ImageProvider
from app.integrations.generation.video.base import GeneratedVideo, VideoProvider


def _poll_until_terminal(client, url, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(url)
        job = resp.json()
        if job["status"] in ("completed", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"Job at {url} did not reach a terminal status within {timeout}s")


class _FakeImageProvider(ImageProvider):
    def __init__(
        self,
        data: bytes = b"\x89PNG\r\n\x1a\nfake-png-bytes",
        fail: bool = False,
        fail_with: Exception | None = None,
    ):
        self._data = data
        self._fail = fail
        self._fail_with = fail_with

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(available=True, provider="fake-openai", mode="production", reason="configured")

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024) -> GeneratedImage:
        if self._fail_with is not None:
            raise self._fail_with
        if self._fail:
            raise GenerationProviderRequestError("Fake OpenAI image generation failed.")
        return GeneratedImage(data=self._data, format="png", content_type="image/png", width=width, height=height)


class _FakeVideoProvider(VideoProvider):
    def __init__(
        self,
        data: bytes = b"fake-mp4-bytes",
        fail: bool = False,
        fail_with: Exception | None = None,
    ):
        self._data = data
        self._fail = fail
        self._fail_with = fail_with
        self.last_reference_image: bytes | None = None

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(available=True, provider="fake-gemini", mode="production", reason="configured")

    async def generate(
        self, prompt: str, duration_seconds: float = 4.0, reference_image: bytes | None = None
    ) -> GeneratedVideo:
        self.last_reference_image = reference_image
        if self._fail_with is not None:
            raise self._fail_with
        if self._fail:
            raise GenerationProviderRequestError("Fake Gemini video generation failed.")
        return GeneratedVideo(data=self._data, format="mp4", content_type="video/mp4", duration_seconds=duration_seconds)


def _signup_second_user(client, email_outbox, email="second-media@example.com"):
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
    client.post("/api/auth/login", json={"email": email, "password": password})


class TestImageGenerationEndpoint:
    def test_requires_authentication(self, client):
        assert client.post("/api/generation/image", json={"prompt": "a cat"}).status_code == 401

    def test_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post("/api/generation/image", json={"prompt": "a cat"})
        assert resp.status_code == 403

    def test_empty_prompt_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post("/api/generation/image", json={"prompt": ""}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 422

    def test_invalid_dimensions_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/generation/image",
            json={"prompt": "a cat", "width": 50, "height": 50},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422

    def test_honestly_fails_when_no_provider_configured(self, auth_client):
        """Default test config has IMAGE_PROVIDER=cloud (the app default —
        image generation is API-based only) but no OPENAI_API_KEY — the
        job must land on `failed` with a real reason, never `completed`
        with fabricated output."""
        client, csrf = auth_client
        resp = client.post("/api/generation/image", json={"prompt": "a red bicycle"}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 202
        job = _poll_until_terminal(client, f"/api/generation/image/{resp.json()['id']}")
        assert job["status"] == "failed"
        assert job["error"]
        assert job["error_type"] == "not_configured"

    def test_quota_exceeded_is_recorded_with_structured_error_type(self, auth_client, monkeypatch):
        """A 429 from OpenAI (real symptom: 'credit_balance_exhausted')
        must never crash the backend or the job — it lands as a `failed`
        job with error_type='quota_exceeded' so the frontend can render a
        dedicated quota-exceeded card with a Retry button instead of a
        generic failure message."""
        client, csrf = auth_client
        import app.jobs.worker as worker_module

        fake = _FakeImageProvider(
            fail_with=GenerationProviderQuotaExceededError(
                "OpenAI image generation failed (429): insufficient_quota"
            )
        )
        monkeypatch.setattr(worker_module, "get_image_provider", lambda: fake)

        resp = client.post("/api/generation/image", json={"prompt": "a red bicycle"}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 202
        job = _poll_until_terminal(client, f"/api/generation/image/{resp.json()['id']}")
        assert job["status"] == "failed"
        assert job["error_type"] == "quota_exceeded"
        assert "429" in job["error"]
        assert "insufficient_quota" in job["error"]

    def test_succeeds_with_configured_provider_and_is_downloadable(self, auth_client, monkeypatch):
        client, csrf = auth_client
        import app.jobs.worker as worker_module

        fake = _FakeImageProvider()
        monkeypatch.setattr(worker_module, "get_image_provider", lambda: fake)

        resp = client.post(
            "/api/generation/image",
            json={"prompt": "a red bicycle on a beach", "width": 512, "height": 512},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 202
        job = _poll_until_terminal(client, f"/api/generation/image/{resp.json()['id']}")
        assert job["status"] == "completed"
        assert job["output_metadata"]["content_type"] == "image/png"

        download = client.get(f"/api/generation/image/{job['id']}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == "image/png"
        assert download.content == fake._data

    def test_project_association_and_invalid_project_rejected(self, auth_client, monkeypatch):
        client, csrf = auth_client
        import app.jobs.worker as worker_module

        monkeypatch.setattr(worker_module, "get_image_provider", lambda: _FakeImageProvider())

        project = client.post("/api/projects", json={"name": "Image Project"}, headers={"X-CSRF-Token": csrf}).json()
        resp = client.post(
            "/api/generation/image",
            json={"prompt": "a cat", "project_id": project["id"]},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 202
        assert resp.json()["project_id"] == project["id"]

        bad = client.post(
            "/api/generation/image",
            json={"prompt": "a cat", "project_id": "00000000-0000-0000-0000-000000000000"},
            headers={"X-CSRF-Token": csrf},
        )
        assert bad.status_code == 404

    def test_generation_is_logged_to_history(self, auth_client, monkeypatch):
        client, csrf = auth_client
        import app.jobs.worker as worker_module

        monkeypatch.setattr(worker_module, "get_image_provider", lambda: _FakeImageProvider())
        resp = client.post("/api/generation/image", json={"prompt": "a cat"}, headers={"X-CSRF-Token": csrf})
        _poll_until_terminal(client, f"/api/generation/image/{resp.json()['id']}")

        history = client.get("/api/history?type=image").json()["items"]
        assert len(history) == 1
        assert history[0]["status"] == "completed"

    def test_video_job_id_not_visible_via_image_routes(self, auth_client):
        client, csrf = auth_client
        video_resp = client.post(
            "/api/generation/video", json={"prompt": "a drone shot"}, headers={"X-CSRF-Token": csrf}
        )
        video_job_id = video_resp.json()["id"]
        assert client.get(f"/api/generation/image/{video_job_id}").status_code == 404
        assert client.get(f"/api/generation/image/{video_job_id}/download").status_code == 404

    def test_isolated_between_users(self, auth_client, client, email_outbox, monkeypatch):
        import app.jobs.worker as worker_module

        monkeypatch.setattr(worker_module, "get_image_provider", lambda: _FakeImageProvider())
        owner_client, owner_csrf = auth_client
        resp = owner_client.post(
            "/api/generation/image", json={"prompt": "owner's private image"}, headers={"X-CSRF-Token": owner_csrf}
        )
        job_id = resp.json()["id"]
        _poll_until_terminal(owner_client, f"/api/generation/image/{job_id}")

        _signup_second_user(client, email_outbox)
        assert client.get(f"/api/generation/image/{job_id}").status_code == 404
        assert client.get(f"/api/generation/image/{job_id}/download").status_code == 404


class TestVideoGenerationEndpoint:
    def test_requires_authentication(self, client):
        assert client.post("/api/generation/video", json={"prompt": "a car"}).status_code == 401

    def test_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        assert client.post("/api/generation/video", json={"prompt": "a car"}).status_code == 403

    def test_empty_prompt_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post("/api/generation/video", json={"prompt": ""}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 422

    def test_invalid_reference_image_base64_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/generation/video",
            json={"prompt": "a car", "reference_image_base64": "not-valid-base64!!"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422

    def test_honestly_fails_when_no_provider_configured(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/generation/video", json={"prompt": "a drone shot"}, headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 202
        job = _poll_until_terminal(client, f"/api/generation/video/{resp.json()['id']}")
        assert job["status"] == "failed"
        assert job["error"]
        assert job["error_type"] == "not_configured"

    def test_quota_exceeded_is_recorded_with_structured_error_type(self, auth_client, monkeypatch):
        """A 429 from Gemini (real symptom: quota exceeded) must never
        crash the backend or the job — it lands as a `failed` job with
        error_type='quota_exceeded' so the frontend can render a
        dedicated quota-exceeded card with a Retry button."""
        client, csrf = auth_client
        import app.jobs.worker as worker_module

        fake = _FakeVideoProvider(
            fail_with=GenerationProviderQuotaExceededError(
                "Gemini video generation request failed (429): RESOURCE_EXHAUSTED"
            )
        )
        monkeypatch.setattr(worker_module, "get_video_provider", lambda: fake)

        resp = client.post("/api/generation/video", json={"prompt": "a drone shot"}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 202
        job = _poll_until_terminal(client, f"/api/generation/video/{resp.json()['id']}")
        assert job["status"] == "failed"
        assert job["error_type"] == "quota_exceeded"
        assert "429" in job["error"]

    def test_succeeds_with_configured_provider_and_is_downloadable(self, auth_client, monkeypatch):
        client, csrf = auth_client
        import app.jobs.worker as worker_module

        fake = _FakeVideoProvider()
        monkeypatch.setattr(worker_module, "get_video_provider", lambda: fake)

        resp = client.post(
            "/api/generation/video",
            json={"prompt": "a drone flying over mountains", "duration_seconds": 5},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 202
        job = _poll_until_terminal(client, f"/api/generation/video/{resp.json()['id']}")
        assert job["status"] == "completed"
        assert job["output_metadata"]["content_type"] == "video/mp4"

        download = client.get(f"/api/generation/video/{job['id']}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == "video/mp4"
        assert download.content == fake._data

    def test_reference_image_is_stored_and_passed_to_provider(self, auth_client, monkeypatch):
        import base64

        client, csrf = auth_client
        import app.jobs.worker as worker_module

        fake = _FakeVideoProvider()
        monkeypatch.setattr(worker_module, "get_video_provider", lambda: fake)

        raw_image = b"\x89PNG\r\n\x1a\nreference-image-bytes"
        resp = client.post(
            "/api/generation/video",
            json={
                "prompt": "animate this image",
                "reference_image_base64": base64.b64encode(raw_image).decode(),
            },
            headers={"X-CSRF-Token": csrf},
        )
        job = _poll_until_terminal(client, f"/api/generation/video/{resp.json()['id']}")
        assert job["status"] == "completed"
        assert fake.last_reference_image == raw_image

    def test_generation_failure_is_recorded_honestly(self, auth_client, monkeypatch):
        client, csrf = auth_client
        import app.jobs.worker as worker_module

        monkeypatch.setattr(worker_module, "get_video_provider", lambda: _FakeVideoProvider(fail=True))
        resp = client.post("/api/generation/video", json={"prompt": "a car"}, headers={"X-CSRF-Token": csrf})
        job = _poll_until_terminal(client, f"/api/generation/video/{resp.json()['id']}")
        assert job["status"] == "failed"
        assert "failed" in job["error"].lower()
        assert job["error_type"] == "generation_failed"

    def test_invalid_project_id_returns_404(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/generation/video",
            json={"prompt": "a car", "project_id": "00000000-0000-0000-0000-000000000000"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 404


class TestWordDocumentGeneration:
    _PAYLOAD = {
        "title": "Quarterly Report",
        "author": "Test Author",
        "blocks": [
            {"type": "heading", "text": "Overview", "level": 1},
            {"type": "paragraph", "text": "This quarter exceeded expectations."},
            {"type": "bullet_list", "items": ["Revenue up", "Churn down"]},
            {"type": "numbered_list", "items": ["Step one", "Step two"]},
            {"type": "table", "rows": [["Metric", "Value"], ["Revenue", "$1.2M"]], "header_row": True},
        ],
    }

    def test_requires_authentication(self, client):
        assert client.post("/api/generation/document/word", json=self._PAYLOAD).status_code == 401

    def test_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        assert client.post("/api/generation/document/word", json=self._PAYLOAD).status_code == 403

    def test_missing_title_rejected(self, auth_client):
        client, csrf = auth_client
        payload = {**self._PAYLOAD, "title": ""}
        resp = client.post("/api/generation/document/word", json=payload, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 422

    def test_empty_blocks_rejected(self, auth_client):
        client, csrf = auth_client
        payload = {**self._PAYLOAD, "blocks": []}
        resp = client.post("/api/generation/document/word", json=payload, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 422

    def test_creates_real_downloadable_docx(self, auth_client):
        client, csrf = auth_client
        resp = client.post("/api/generation/document/word", json=self._PAYLOAD, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 201
        body = resp.json()
        assert body["format"] == "docx"
        assert body["status"] == "completed"
        assert body["title"] == "Quarterly Report"

        download = client.get(f"/api/documents/{body['id']}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert download.content[:2] == b"PK"
        zf = zipfile.ZipFile(io.BytesIO(download.content))
        assert "word/document.xml" in zf.namelist()

    def test_project_association(self, auth_client):
        client, csrf = auth_client
        project = client.post("/api/projects", json={"name": "Docs"}, headers={"X-CSRF-Token": csrf}).json()
        payload = {**self._PAYLOAD, "project_id": project["id"]}
        resp = client.post("/api/generation/document/word", json=payload, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 201
        assert resp.json()["project_id"] == project["id"]

    def test_invalid_project_id_returns_404(self, auth_client):
        client, csrf = auth_client
        payload = {**self._PAYLOAD, "project_id": "00000000-0000-0000-0000-000000000000"}
        resp = client.post("/api/generation/document/word", json=payload, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 404

    def test_logged_to_history(self, auth_client):
        client, csrf = auth_client
        client.post("/api/generation/document/word", json=self._PAYLOAD, headers={"X-CSRF-Token": csrf})
        items = client.get("/api/history?type=document").json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "completed"
        assert "Word" in items[0]["title"]

    def test_isolated_between_users(self, auth_client, client, email_outbox):
        owner_client, owner_csrf = auth_client
        resp = owner_client.post(
            "/api/generation/document/word", json=self._PAYLOAD, headers={"X-CSRF-Token": owner_csrf}
        )
        doc_id = resp.json()["id"]

        _signup_second_user(client, email_outbox)
        assert client.get(f"/api/documents/{doc_id}").status_code == 404
        assert client.get(f"/api/documents/{doc_id}/download").status_code == 404


class TestPptDocumentGeneration:
    _PAYLOAD = {
        "title": "Product Launch",
        "subtitle": "Q3 2026",
        "slides": [
            {
                "title": "Agenda",
                "layout": "title_content",
                "bullets": ["Problem", "Solution", "Roadmap"],
                "notes": "Keep it brief",
            },
            {"title": "Thank You", "layout": "section_header"},
        ],
    }

    def test_requires_authentication(self, client):
        assert client.post("/api/generation/document/ppt", json=self._PAYLOAD).status_code == 401

    def test_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        assert client.post("/api/generation/document/ppt", json=self._PAYLOAD).status_code == 403

    def test_empty_slides_rejected(self, auth_client):
        client, csrf = auth_client
        payload = {**self._PAYLOAD, "slides": []}
        resp = client.post("/api/generation/document/ppt", json=payload, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 422

    def test_creates_real_downloadable_pptx(self, auth_client):
        client, csrf = auth_client
        resp = client.post("/api/generation/document/ppt", json=self._PAYLOAD, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 201
        body = resp.json()
        assert body["format"] == "pptx"
        assert body["status"] == "completed"

        download = client.get(f"/api/documents/{body['id']}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
        assert download.content[:2] == b"PK"
        zf = zipfile.ZipFile(io.BytesIO(download.content))
        slide_files = [n for n in zf.namelist() if n.startswith("ppt/slides/slide")]
        # 1 title slide + 2 spec'd slides = 3
        assert len(slide_files) == 3

    def test_logged_to_history(self, auth_client):
        client, csrf = auth_client
        client.post("/api/generation/document/ppt", json=self._PAYLOAD, headers={"X-CSRF-Token": csrf})
        items = client.get("/api/history?type=document").json()["items"]
        assert len(items) == 1
        assert "Presentation" in items[0]["title"]


class TestExcelDocumentGeneration:
    _PAYLOAD = {
        "title": "Sales Data",
        "sheets": [
            {
                "name": "Sales",
                "headers": ["Month", "Revenue"],
                "rows": [["Jan", 100], ["Feb", 150], ["Mar", 175]],
                "charts": [
                    {
                        "type": "line",
                        "title": "Revenue Trend",
                        "category_column": "Month",
                        "value_columns": ["Revenue"],
                    }
                ],
            }
        ],
    }

    def test_requires_authentication(self, client):
        assert client.post("/api/generation/document/excel", json=self._PAYLOAD).status_code == 401

    def test_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        assert client.post("/api/generation/document/excel", json=self._PAYLOAD).status_code == 403

    def test_empty_sheets_rejected(self, auth_client):
        client, csrf = auth_client
        payload = {**self._PAYLOAD, "sheets": []}
        resp = client.post("/api/generation/document/excel", json=payload, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 422

    def test_sheet_name_too_long_rejected(self, auth_client):
        client, csrf = auth_client
        payload = {
            "title": "Sales Data",
            "sheets": [{**self._PAYLOAD["sheets"][0], "name": "x" * 32}],
        }
        resp = client.post("/api/generation/document/excel", json=payload, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 422

    def test_creates_real_downloadable_xlsx_with_chart(self, auth_client):
        client, csrf = auth_client
        resp = client.post("/api/generation/document/excel", json=self._PAYLOAD, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 201
        body = resp.json()
        assert body["format"] == "xlsx"
        assert body["status"] == "completed"

        download = client.get(f"/api/documents/{body['id']}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert download.content[:2] == b"PK"
        zf = zipfile.ZipFile(io.BytesIO(download.content))
        assert any(n.startswith("xl/charts/") for n in zf.namelist())

    def test_creates_valid_xlsx_without_chart(self, auth_client):
        client, csrf = auth_client
        payload = {
            "title": "Plain Data",
            "sheets": [{"name": "Data", "headers": ["A", "B"], "rows": [[1, 2], [3, 4]]}],
        }
        resp = client.post("/api/generation/document/excel", json=payload, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 201
        download = client.get(f"/api/documents/{resp.json()['id']}/download")
        zf = zipfile.ZipFile(io.BytesIO(download.content))
        assert "xl/worksheets/sheet1.xml" in zf.namelist()

    def test_logged_to_history(self, auth_client):
        client, csrf = auth_client
        client.post("/api/generation/document/excel", json=self._PAYLOAD, headers={"X-CSRF-Token": csrf})
        items = client.get("/api/history?type=document").json()["items"]
        assert len(items) == 1
        assert "Spreadsheet" in items[0]["title"]


class TestStructuredFormatsRejectedOnAiDraftedEndpoint:
    """The AI-drafted /api/documents endpoint takes a free-text prompt and
    only knows how to render markdown/docx/pdf from it — pptx/xlsx must be
    created via the structured /api/generation/document/* endpoints
    instead, never silently mis-rendered as markdown under a pptx/xlsx
    label (see CreateDocumentRequest._validate_format)."""

    def test_pptx_format_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/documents",
            json={"prompt": "Write something.", "format": "pptx"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422

    def test_xlsx_format_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/documents",
            json={"prompt": "Write something.", "format": "xlsx"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422


class TestStructuredRenderersProduceValidFiles:
    """Direct unit coverage of the renderers themselves (no HTTP/DB), to
    pin down exact byte-level output shape independent of the API layer."""

    def test_render_structured_docx_is_valid_zip_with_document_xml(self):
        from app.documents.structured_render import render_structured_docx
        from app.schemas.generation import WordDocumentRequest

        data = render_structured_docx(
            WordDocumentRequest(title="T", blocks=[{"type": "paragraph", "text": "hi"}])
        )
        assert data[:2] == b"PK"
        zf = zipfile.ZipFile(io.BytesIO(data))
        assert "word/document.xml" in zf.namelist()

    def test_render_pptx_is_valid_zip(self):
        from app.documents.structured_render import render_pptx
        from app.schemas.generation import PptDocumentRequest

        data = render_pptx(PptDocumentRequest(title="T", slides=[{"title": "S1", "bullets": ["a"]}]))
        assert data[:2] == b"PK"
        zf = zipfile.ZipFile(io.BytesIO(data))
        assert any(n.startswith("ppt/slides/slide") for n in zf.namelist())

    def test_render_xlsx_is_valid_zip(self):
        from app.documents.structured_render import render_xlsx
        from app.schemas.generation import ExcelDocumentRequest

        data = render_xlsx(
            ExcelDocumentRequest(title="T", sheets=[{"name": "S", "headers": ["A"], "rows": [[1]]}])
        )
        assert data[:2] == b"PK"
        zf = zipfile.ZipFile(io.BytesIO(data))
        assert "xl/worksheets/sheet1.xml" in zf.namelist()
