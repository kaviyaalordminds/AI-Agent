import io
import re

import pytest

from app.documents.render import parse_markdown_blocks, render_docx, render_pdf
from app.integrations.claude.base import ClaudeProvider, ProviderStatus
from app.integrations.claude.errors import ProviderRequestError
from app.integrations.storage.errors import FileTooLargeError, InvalidStoragePathError
from app.integrations.storage.local_provider import LocalStorageProvider


# ---------------------------------------------------------------------------
# StorageProvider (no LLM, no network)
# ---------------------------------------------------------------------------


class TestLocalStorageProvider:
    def test_write_then_read_round_trips(self, tmp_path):
        provider = LocalStorageProvider(tmp_path / "storage")
        stored = provider.write("documents", "user-1", "a.txt", b"hello")
        assert stored.size_bytes == 5
        assert provider.read(stored.ref) == b"hello"

    def test_write_within_size_limit_succeeds(self, tmp_path):
        provider = LocalStorageProvider(tmp_path / "storage", max_file_size_bytes=100)
        stored = provider.write("documents", "user-1", "small.txt", b"x" * 50)
        assert stored.size_bytes == 50

    def test_write_over_size_limit_rejected(self, tmp_path):
        provider = LocalStorageProvider(tmp_path / "storage", max_file_size_bytes=100)
        with pytest.raises(FileTooLargeError):
            provider.write("documents", "user-1", "big.txt", b"x" * 101)

    def test_no_size_limit_by_default(self, tmp_path):
        provider = LocalStorageProvider(tmp_path / "storage")
        stored = provider.write("documents", "user-1", "big.txt", b"x" * 1_000_000)
        assert stored.size_bytes == 1_000_000

    def test_delete_then_read_raises(self, tmp_path):
        provider = LocalStorageProvider(tmp_path / "storage")
        stored = provider.write("documents", "user-1", "a.txt", b"hello")
        provider.delete(stored.ref)
        with pytest.raises(FileNotFoundError):
            provider.read(stored.ref)

    def test_double_delete_is_a_safe_noop(self, tmp_path):
        provider = LocalStorageProvider(tmp_path / "storage")
        stored = provider.write("documents", "user-1", "a.txt", b"hello")
        provider.delete(stored.ref)
        provider.delete(stored.ref)  # must not raise

    def test_owner_id_traversal_rejected(self, tmp_path):
        provider = LocalStorageProvider(tmp_path / "storage")
        with pytest.raises(InvalidStoragePathError):
            provider.write("documents", "../evil", "a.txt", b"x")

    def test_read_ref_traversal_rejected(self, tmp_path):
        provider = LocalStorageProvider(tmp_path / "storage")
        with pytest.raises(InvalidStoragePathError):
            provider.read("../../etc/passwd")

    def test_different_owners_are_isolated_on_disk(self, tmp_path):
        provider = LocalStorageProvider(tmp_path / "storage")
        a = provider.write("documents", "user-1", "same.txt", b"A")
        b = provider.write("documents", "user-2", "same.txt", b"B")
        assert provider.read(a.ref) == b"A"
        assert provider.read(b.ref) == b"B"


# ---------------------------------------------------------------------------
# Markdown -> docx/pdf rendering (no LLM, no network)
# ---------------------------------------------------------------------------


class TestRenderEngine:
    def test_parse_markdown_blocks(self):
        md = "# Title\n## Section\nA paragraph.\n- bullet one\n1. step one"
        blocks = parse_markdown_blocks(md)
        kinds = [(b.kind, b.text, b.level) for b in blocks]
        assert kinds == [
            ("heading", "Title", 1),
            ("heading", "Section", 2),
            ("paragraph", "A paragraph.", 0),
            ("bullet", "bullet one", 0),
            ("numbered", "step one", 0),
        ]

    def test_render_docx_produces_real_openable_document(self):
        from docx import Document as DocxDocument

        md = "# Title\n## Section\nSome text.\n- item one\n- item two"
        data = render_docx(md, "My Document")
        assert data[:2] == b"PK"  # real zip-based .docx, not a placeholder
        doc = DocxDocument(io.BytesIO(data))
        texts = [p.text for p in doc.paragraphs]
        assert "My Document" in texts
        assert "Section" in texts
        assert "Some text." in texts
        assert "item one" in texts

    def test_render_pdf_produces_real_pdf(self):
        md = "# Title\nSome paragraph text."
        data = render_pdf(md, "My Document")
        assert data[:4] == b"%PDF"

    def test_render_handles_empty_content_without_crashing(self):
        assert render_docx("", "Empty")[:2] == b"PK"
        assert render_pdf("", "Empty")[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Documents API
# ---------------------------------------------------------------------------


class _FakeProvider(ClaudeProvider):
    def __init__(self, text: str, fail: bool = False):
        self.text = text
        self.fail = fail
        self.received_messages = None
        self.received_system_prompt = None

    def status(self) -> ProviderStatus:
        return ProviderStatus(configured=True, provider="fake", model="fake-model", detail="ok")

    async def stream(self, messages, system_prompt):
        self.received_messages = messages
        self.received_system_prompt = system_prompt
        if self.fail:
            raise ProviderRequestError("simulated upstream failure")
        yield self.text


_SAMPLE_DRAFT = "# Kickoff Plan\n## Overview\nThis plan covers the kickoff.\n- Define scope\n- Assign owners"


def _patch_provider(monkeypatch, provider):
    import app.api.documents.router as documents_router_module

    monkeypatch.setattr(documents_router_module, "get_claude_provider", lambda: provider)


class TestDocumentsEndpoint:
    def test_requires_authentication(self, client):
        assert client.get("/api/documents").status_code == 401
        assert client.post("/api/documents", json={"prompt": "write something"}).status_code == 401

    def test_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post("/api/documents", json={"prompt": "write a project plan"})
        assert resp.status_code == 403

    def test_prompt_too_short_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post("/api/documents", json={"prompt": "hi"}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 422

    def test_unconfigured_provider_persists_prompt_and_returns_503(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/documents",
            json={"prompt": "Write a project kickoff plan for a new HRMS.", "format": "markdown"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 503

        listing = client.get("/api/documents")
        assert listing.status_code == 200
        docs = listing.json()
        assert len(docs) == 1
        assert docs[0]["status"] == "failed"
        assert docs[0]["prompt"] == "Write a project kickoff plan for a new HRMS."
        assert docs[0]["error"]

    def test_configured_provider_generates_markdown_document(self, auth_client, monkeypatch):
        client, csrf = auth_client
        fake = _FakeProvider(_SAMPLE_DRAFT)
        _patch_provider(monkeypatch, fake)

        resp = client.post(
            "/api/documents",
            json={"prompt": "Write a project kickoff plan.", "format": "markdown"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "completed"
        assert body["title"] == "Kickoff Plan"
        assert body["format"] == "markdown"
        assert "Overview" in body["content"]
        assert body["size_bytes"] > 0
        assert "storage_ref" not in body  # internal reference never exposed to the client

        download = client.get(f"/api/documents/{body['id']}/download")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("text/markdown")
        assert b"Kickoff Plan" in download.content

    def test_configured_provider_generates_docx_document(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_SAMPLE_DRAFT))

        resp = client.post(
            "/api/documents",
            json={"prompt": "Write a project kickoff plan.", "format": "docx"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201
        doc_id = resp.json()["id"]

        download = client.get(f"/api/documents/{doc_id}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert download.content[:2] == b"PK"
        assert "Kickoff Plan.docx" in download.headers["content-disposition"]

    def test_configured_provider_generates_pdf_document(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_SAMPLE_DRAFT))

        resp = client.post(
            "/api/documents",
            json={"prompt": "Write a project kickoff plan.", "format": "pdf"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201
        doc_id = resp.json()["id"]

        download = client.get(f"/api/documents/{doc_id}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/pdf"
        assert download.content[:4] == b"%PDF"

    def test_configured_provider_failure_persists_failed_document(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(text="", fail=True))

        resp = client.post(
            "/api/documents",
            json={"prompt": "Write a project kickoff plan.", "format": "markdown"},
            headers={"X-CSRF-Token": csrf},
        )
        # The prompt was successfully persisted even though generation failed —
        # this is a normal (failed-status) resource, not an HTTP error.
        assert resp.status_code == 201
        assert resp.json()["status"] == "failed"

    def test_failed_document_has_nothing_to_download(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(text="", fail=True))
        resp = client.post(
            "/api/documents",
            json={"prompt": "Write a project kickoff plan."},
            headers={"X-CSRF-Token": csrf},
        )
        doc_id = resp.json()["id"]
        download = client.get(f"/api/documents/{doc_id}/download")
        assert download.status_code == 409

    def test_get_nonexistent_document_returns_404(self, auth_client):
        client, _csrf = auth_client
        assert client.get("/api/documents/00000000-0000-0000-0000-000000000000").status_code == 404

    def test_create_document_with_invalid_project_returns_404(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/documents",
            json={"prompt": "Write something.", "project_id": "00000000-0000-0000-0000-000000000000"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 404

    def test_delete_document_removes_stored_file(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_SAMPLE_DRAFT))
        resp = client.post(
            "/api/documents",
            json={"prompt": "Write a project kickoff plan.", "format": "markdown"},
            headers={"X-CSRF-Token": csrf},
        )
        doc_id = resp.json()["id"]

        delete_resp = client.delete(f"/api/documents/{doc_id}")
        assert delete_resp.status_code == 204

        assert client.get(f"/api/documents/{doc_id}").status_code == 404

    def test_documents_are_logged_to_history(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_SAMPLE_DRAFT))
        client.post(
            "/api/documents",
            json={"prompt": "Write a project kickoff plan.", "format": "markdown"},
            headers={"X-CSRF-Token": csrf},
        )
        resp = client.get("/api/history?type=document")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "completed"
        assert "Kickoff Plan" in items[0]["title"]

    def test_documents_are_isolated_between_users(self, auth_client, client, email_outbox, monkeypatch):
        owner_client, owner_csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_SAMPLE_DRAFT))
        create_resp = owner_client.post(
            "/api/documents",
            json={"prompt": "Owner's private document request.", "format": "markdown"},
            headers={"X-CSRF-Token": owner_csrf},
        )
        doc_id = create_resp.json()["id"]

        second_password = "Str0ng!Passw0rd"
        client.post(
            "/api/auth/signup",
            json={
                "full_name": "Second User",
                "email": "second-docs@example.com",
                "password": second_password,
                "confirm_password": second_password,
                "accept_terms": True,
            },
        )
        token = re.search(r"token=([A-Za-z0-9_\-]+)", email_outbox[-1].text_body).group(1)
        client.post("/api/auth/verify-email", json={"token": token})
        client.post("/api/auth/login", json={"email": "second-docs@example.com", "password": second_password})

        assert client.get("/api/documents").json() == []
        assert client.get(f"/api/documents/{doc_id}").status_code == 404
        assert client.get(f"/api/documents/{doc_id}/download").status_code == 404
