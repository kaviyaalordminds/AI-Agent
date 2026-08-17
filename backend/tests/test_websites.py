"""Tests for Website generation (Phase 8, Developer Studio):
POST /api/websites (AI-drafted multi-page static site via Claude, backed
by the same StorageProvider pattern as Documents), the preview/deploy
endpoints, and "3D Website" (style="3d" on this exact same pipeline, not
a separate module).

Generation itself runs as a background asyncio task (see
app/websites/generator.py) rather than inside the request/response
cycle, so POST /api/websites returns 202 with status="processing"
immediately; these tests poll GET /api/websites/{id} for the real final
status the same way the real frontend does.
"""
import json
import time
import zipfile
from io import BytesIO

from app.integrations.claude.base import ClaudeProvider, ProviderStatus
from app.integrations.claude.errors import ProviderRequestError


def _poll_until_terminal(client, website_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    body = None
    while time.monotonic() < deadline:
        body = client.get(f"/api/websites/{website_id}").json()
        if body["status"] != "processing":
            return body
        time.sleep(0.02)
    raise AssertionError(f"Website {website_id} did not leave 'processing' within {timeout}s: {body}")


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


def _sample_pages_json(count: int = 2) -> str:
    pages = [f"<!DOCTYPE html><html><head><title>Page {i}</title></head><body>Page {i} content</body></html>" for i in range(count)]
    return json.dumps({"pages": pages})


def _patch_provider(monkeypatch, provider):
    import app.api.websites.router as websites_router_module

    monkeypatch.setattr(websites_router_module, "get_claude_provider", lambda: provider)


class TestWebsitesEndpoint:
    def test_requires_authentication(self, client):
        assert client.get("/api/websites").status_code == 401
        assert client.post("/api/websites", json={"name": "My Site", "prompt": "a portfolio site"}).status_code == 401

    def test_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post("/api/websites", json={"name": "My Site", "prompt": "a portfolio site"})
        assert resp.status_code == 403

    def test_prompt_too_short_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/websites", json={"name": "My Site", "prompt": "hi"}, headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 422

    def test_empty_pages_list_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/websites",
            json={"name": "My Site", "prompt": "a portfolio site", "pages": []},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422

    def test_invalid_style_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/websites",
            json={"name": "My Site", "prompt": "a portfolio site", "style": "not-a-real-style"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422

    def test_unconfigured_provider_persists_prompt_and_returns_503(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/websites",
            json={"name": "My Portfolio", "prompt": "a personal portfolio site"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 503

        listing = client.get("/api/websites").json()
        assert len(listing) == 1
        assert listing[0]["status"] == "failed"
        assert listing[0]["name"] == "My Portfolio"
        assert listing[0]["error"]

    def test_generates_pages_with_index_and_slugified_filenames(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_sample_pages_json(3)))

        resp = client.post(
            "/api/websites",
            json={
                "name": "Acme Studio",
                "prompt": "a small design studio site",
                "pages": ["Home", "About Us", "Contact"],
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 202
        assert resp.json()["status"] == "processing"

        body = _poll_until_terminal(client, resp.json()["id"])
        assert body["status"] == "completed"
        assert len(body["pages"]) == 3
        assert body["pages"][0]["path"] == "index.html"
        assert body["pages"][1]["path"] == "about-us.html"
        assert body["pages"][2]["path"] == "contact.html"
        assert all("storage_ref" not in p for p in body["pages"])

    def test_malformed_ai_response_recorded_as_failed_not_fabricated(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider("Sorry, I can't format that as JSON right now."))

        resp = client.post(
            "/api/websites",
            json={"name": "My Site", "prompt": "a portfolio site"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 202

        body = _poll_until_terminal(client, resp.json()["id"])
        assert body["status"] == "failed"
        assert body["pages"] == []
        assert body["error"]

    def test_upstream_failure_recorded_as_failed(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider("", fail=True))

        resp = client.post(
            "/api/websites",
            json={"name": "My Site", "prompt": "a portfolio site"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 202

        body = _poll_until_terminal(client, resp.json()["id"])
        assert body["status"] == "failed"

    def test_3d_style_is_accepted_and_generates_normally(self, auth_client, monkeypatch):
        client, csrf = auth_client
        fake = _FakeProvider(_sample_pages_json(1))
        _patch_provider(monkeypatch, fake)

        resp = client.post(
            "/api/websites",
            json={"name": "3D Showcase", "prompt": "an interactive 3D landing page", "style": "3d", "pages": ["Home"]},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 202
        assert resp.json()["style"] == "3d"

        body = _poll_until_terminal(client, resp.json()["id"])
        assert body["status"] == "completed"
        assert "3d" in fake.received_messages[0].content.lower()

    def test_preview_serves_generated_html(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_sample_pages_json(1)))
        website_id = client.post(
            "/api/websites", json={"name": "My Site", "prompt": "a portfolio site", "pages": ["Home"]},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]
        _poll_until_terminal(client, website_id)

        resp = client.get(f"/api/websites/{website_id}/preview/index.html")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert b"<!DOCTYPE html>" in resp.content

    def test_preview_unknown_page_404(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_sample_pages_json(1)))
        website_id = client.post(
            "/api/websites", json={"name": "My Site", "prompt": "a portfolio site", "pages": ["Home"]},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]

        resp = client.get(f"/api/websites/{website_id}/preview/does-not-exist.html")
        assert resp.status_code == 404

    def test_project_association_and_invalid_project_rejected(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_sample_pages_json(1)))

        project = client.post("/api/projects", json={"name": "Website Project"}, headers={"X-CSRF-Token": csrf}).json()
        resp = client.post(
            "/api/websites",
            json={"name": "My Site", "prompt": "a portfolio site", "project_id": project["id"]},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 202
        assert resp.json()["project_id"] == project["id"]

        bad = client.post(
            "/api/websites",
            json={"name": "My Site", "prompt": "a portfolio site", "project_id": "00000000-0000-0000-0000-000000000000"},
            headers={"X-CSRF-Token": csrf},
        )
        assert bad.status_code == 404

    def test_generation_is_logged_to_history(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_sample_pages_json(1)))
        website_id = client.post(
            "/api/websites", json={"name": "My Site", "prompt": "a portfolio site", "pages": ["Home"]},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]
        _poll_until_terminal(client, website_id)

        history = client.get("/api/history?type=website").json()["items"]
        assert len(history) == 1
        assert history[0]["status"] == "completed"

    def test_delete_removes_website_and_stored_files(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_sample_pages_json(1)))
        website_id = client.post(
            "/api/websites", json={"name": "My Site", "prompt": "a portfolio site", "pages": ["Home"]},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]
        _poll_until_terminal(client, website_id)

        resp = client.delete(f"/api/websites/{website_id}", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 204
        assert client.get(f"/api/websites/{website_id}").status_code == 404
        assert client.get(f"/api/websites/{website_id}/preview/index.html").status_code == 404

    def test_isolated_between_users(self, auth_client, client, email_outbox, monkeypatch):
        import re

        _patch_provider(monkeypatch, _FakeProvider(_sample_pages_json(1)))
        owner_client, owner_csrf = auth_client
        website_id = owner_client.post(
            "/api/websites", json={"name": "Private Site", "prompt": "a private portfolio"},
            headers={"X-CSRF-Token": owner_csrf},
        ).json()["id"]
        _poll_until_terminal(owner_client, website_id)

        password = "Str0ng!Passw0rd"
        client.post(
            "/api/auth/signup",
            json={
                "full_name": "Second User",
                "email": "second-website@example.com",
                "password": password,
                "confirm_password": password,
                "accept_terms": True,
            },
        )
        token = re.search(r"token=([A-Za-z0-9_\-]+)", email_outbox[-1].text_body).group(1)
        client.post("/api/auth/verify-email", json={"token": token})
        client.post("/api/auth/login", json={"email": "second-website@example.com", "password": password})

        assert client.get(f"/api/websites/{website_id}").status_code == 404
        assert client.get(f"/api/websites/{website_id}/preview/index.html").status_code == 404


class TestWebsiteDeployment:
    def test_deploy_local_produces_downloadable_zip(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_sample_pages_json(2)))
        website_id = client.post(
            "/api/websites",
            json={"name": "My Site", "prompt": "a portfolio site", "pages": ["Home", "About"]},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]
        _poll_until_terminal(client, website_id)

        resp = client.post(f"/api/websites/{website_id}/deploy", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "local"
        assert body["downloadable"] is True
        assert body["live_url"] is None

        download = client.get(f"/api/websites/{website_id}/deployment/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/zip"
        archive = zipfile.ZipFile(BytesIO(download.content))
        assert set(archive.namelist()) == {"index.html", "about.html"}

    def test_deploy_requires_completed_website_with_pages(self, auth_client):
        client, csrf = auth_client
        # No provider configured -> the create call 503s, but the website
        # still gets persisted as failed (with no pages) — fetch that row.
        client.post("/api/websites", json={"name": "My Site", "prompt": "a portfolio site"}, headers={"X-CSRF-Token": csrf})
        website_id = client.get("/api/websites").json()[0]["id"]

        resp = client.post(f"/api/websites/{website_id}/deploy", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 409

    def test_deploy_requires_csrf(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_sample_pages_json(1)))
        website_id = client.post(
            "/api/websites", json={"name": "My Site", "prompt": "a portfolio site", "pages": ["Home"]},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]
        _poll_until_terminal(client, website_id)

        resp = client.post(f"/api/websites/{website_id}/deploy")
        assert resp.status_code == 403

    def test_deploy_is_logged_to_history_as_deployment(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_sample_pages_json(1)))
        website_id = client.post(
            "/api/websites", json={"name": "My Site", "prompt": "a portfolio site", "pages": ["Home"]},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]
        _poll_until_terminal(client, website_id)
        client.post(f"/api/websites/{website_id}/deploy", headers={"X-CSRF-Token": csrf})

        history = client.get("/api/history?type=deployment").json()["items"]
        assert len(history) == 1
        assert history[0]["status"] == "completed"

    def test_download_before_deploy_returns_409(self, auth_client, monkeypatch):
        client, csrf = auth_client
        _patch_provider(monkeypatch, _FakeProvider(_sample_pages_json(1)))
        website_id = client.post(
            "/api/websites", json={"name": "My Site", "prompt": "a portfolio site", "pages": ["Home"]},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]

        resp = client.get(f"/api/websites/{website_id}/deployment/download")
        assert resp.status_code == 409
