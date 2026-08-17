"""Tests for the Deployments module (app/api/deployments/router.py):
a first-class, trackable deployment record/lifecycle (draft -> deploying
-> active/failed, plus stopped) distinct from Website Studio's own
inline one-shot POST /websites/{id}/deploy (tested separately in
test_websites.py, and left completely unchanged by this module).
"""
from tests.test_websites import _FakeProvider, _patch_provider, _poll_until_terminal, _sample_pages_json


def _create_completed_website(client, csrf, monkeypatch, name="My Site", pages=None):
    _patch_provider(monkeypatch, _FakeProvider(_sample_pages_json(len(pages) if pages else 1)))
    resp = client.post(
        "/api/websites",
        json={"name": name, "prompt": "a portfolio site", "pages": pages or ["Home"]},
        headers={"X-CSRF-Token": csrf},
    )
    website_id = resp.json()["id"]
    body = None
    import time

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        body = client.get(f"/api/websites/{website_id}").json()
        if body["status"] != "processing":
            break
        time.sleep(0.02)
    assert body["status"] == "completed", body
    return website_id


class TestDeploymentsCrud:
    def test_requires_authentication(self, client):
        assert client.get("/api/deployments").status_code == 401
        assert client.post("/api/deployments", json={"website_id": "00000000-0000-0000-0000-000000000000"}).status_code == 401

    def test_requires_csrf(self, auth_client, monkeypatch):
        client, csrf = auth_client
        website_id = _create_completed_website(client, csrf, monkeypatch)
        resp = client.post("/api/deployments", json={"website_id": website_id})
        assert resp.status_code == 403

    def test_invalid_website_id_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/deployments",
            json={"website_id": "00000000-0000-0000-0000-000000000000"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 404

    def test_create_starts_as_draft_and_defaults_name_to_website_name(self, auth_client, monkeypatch):
        client, csrf = auth_client
        website_id = _create_completed_website(client, csrf, monkeypatch, name="Acme Site")
        resp = client.post("/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "draft"
        assert body["name"] == "Acme Site"
        assert body["environment"] == "production"
        assert body["deployment_type"] == "website"
        assert body["live_url"] is None
        assert body["downloadable"] is False

    def test_3d_website_reported_as_website_3d_type(self, auth_client, monkeypatch):
        client, csrf = auth_client
        fake = _FakeProvider(_sample_pages_json(1))
        _patch_provider(monkeypatch, fake)
        resp = client.post(
            "/api/websites",
            json={"name": "3D Site", "prompt": "an interactive 3D landing page", "style": "3d", "pages": ["Home"]},
            headers={"X-CSRF-Token": csrf},
        )
        website_id = resp.json()["id"]
        import time

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            body = client.get(f"/api/websites/{website_id}").json()
            if body["status"] != "processing":
                break
            time.sleep(0.02)

        dep = client.post("/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": csrf})
        assert dep.json()["deployment_type"] == "website_3d"

    def test_custom_name_and_staging_environment(self, auth_client, monkeypatch):
        client, csrf = auth_client
        website_id = _create_completed_website(client, csrf, monkeypatch)
        resp = client.post(
            "/api/deployments",
            json={"website_id": website_id, "name": "Custom Deployment Name", "environment": "staging"},
            headers={"X-CSRF-Token": csrf},
        )
        body = resp.json()
        assert body["name"] == "Custom Deployment Name"
        assert body["environment"] == "staging"

    def test_list_and_get(self, auth_client, monkeypatch):
        client, csrf = auth_client
        website_id = _create_completed_website(client, csrf, monkeypatch)
        created = client.post("/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": csrf}).json()

        listing = client.get("/api/deployments").json()
        assert len(listing) == 1
        assert listing[0]["id"] == created["id"]

        fetched = client.get(f"/api/deployments/{created['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == created["id"]

    def test_get_nonexistent_returns_404(self, auth_client):
        client, _csrf = auth_client
        assert client.get("/api/deployments/00000000-0000-0000-0000-000000000000").status_code == 404

    def test_update_name_and_environment(self, auth_client, monkeypatch):
        client, csrf = auth_client
        website_id = _create_completed_website(client, csrf, monkeypatch)
        created = client.post("/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": csrf}).json()

        resp = client.patch(
            f"/api/deployments/{created['id']}",
            json={"name": "Renamed", "environment": "staging"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"
        assert resp.json()["environment"] == "staging"

    def test_delete_removes_deployment_but_not_website(self, auth_client, monkeypatch):
        client, csrf = auth_client
        website_id = _create_completed_website(client, csrf, monkeypatch)
        created = client.post("/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": csrf}).json()

        resp = client.delete(f"/api/deployments/{created['id']}", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 204
        assert client.get(f"/api/deployments/{created['id']}").status_code == 404
        # The source website must be untouched.
        assert client.get(f"/api/websites/{website_id}").status_code == 200

    def test_isolated_between_users(self, auth_client, client, email_outbox, monkeypatch):
        import re

        owner_client, owner_csrf = auth_client
        website_id = _create_completed_website(owner_client, owner_csrf, monkeypatch)
        created = owner_client.post(
            "/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": owner_csrf}
        ).json()

        password = "Str0ng!Passw0rd"
        client.post(
            "/api/auth/signup",
            json={
                "full_name": "Second User",
                "email": "second-deploy@example.com",
                "password": password,
                "confirm_password": password,
                "accept_terms": True,
            },
        )
        token = re.search(r"token=([A-Za-z0-9_\-]+)", email_outbox[-1].text_body).group(1)
        client.post("/api/auth/verify-email", json={"token": token})
        second_login = client.post(
            "/api/auth/login", json={"email": "second-deploy@example.com", "password": password}
        )
        second_csrf = second_login.cookies["aiagent_csrf"]

        assert client.get(f"/api/deployments/{created['id']}").status_code == 404
        assert client.get("/api/deployments").json() == []

        # The second user also cannot create a NEW deployment referencing
        # the first user's website — website ownership is checked, not
        # just deployment ownership.
        bad = client.post(
            "/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": second_csrf}
        )
        assert bad.status_code == 404


class TestDeploymentExecution:
    def test_deploy_requires_csrf(self, auth_client, monkeypatch):
        client, csrf = auth_client
        website_id = _create_completed_website(client, csrf, monkeypatch)
        created = client.post("/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": csrf}).json()
        resp = client.post(f"/api/deployments/{created['id']}/deploy")
        assert resp.status_code == 403

    def test_deploy_succeeds_with_local_provider_and_is_downloadable(self, auth_client, monkeypatch):
        client, csrf = auth_client
        website_id = _create_completed_website(client, csrf, monkeypatch, pages=["Home", "About"])
        created = client.post("/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": csrf}).json()

        resp = client.post(f"/api/deployments/{created['id']}/deploy", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "active"
        assert body["provider"] == "local"
        assert body["downloadable"] is True
        assert body["deployed_at"] is not None

        download = client.get(f"/api/deployments/{created['id']}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/zip"

    def test_deploy_without_pages_returns_409(self, auth_client, monkeypatch):
        client, csrf = auth_client
        # No provider configured -> website creation 503s but the row is
        # still persisted as failed (no pages) — fetch it and try to deploy.
        client.post(
            "/api/websites", json={"name": "My Site", "prompt": "a portfolio site"}, headers={"X-CSRF-Token": csrf}
        )
        website_id = client.get("/api/websites").json()[0]["id"]
        created = client.post("/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": csrf}).json()

        resp = client.post(f"/api/deployments/{created['id']}/deploy", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 409

    def test_deploy_is_logged_to_history(self, auth_client, monkeypatch):
        client, csrf = auth_client
        website_id = _create_completed_website(client, csrf, monkeypatch)
        created = client.post("/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": csrf}).json()
        client.post(f"/api/deployments/{created['id']}/deploy", headers={"X-CSRF-Token": csrf})

        history = client.get("/api/history?type=deployment").json()["items"]
        assert len(history) == 1
        assert history[0]["status"] == "completed"

    def test_redeploy_after_active_is_allowed(self, auth_client, monkeypatch):
        client, csrf = auth_client
        website_id = _create_completed_website(client, csrf, monkeypatch)
        created = client.post("/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": csrf}).json()
        client.post(f"/api/deployments/{created['id']}/deploy", headers={"X-CSRF-Token": csrf})

        resp = client.post(f"/api/deployments/{created['id']}/deploy", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_stop_requires_active_status(self, auth_client, monkeypatch):
        client, csrf = auth_client
        website_id = _create_completed_website(client, csrf, monkeypatch)
        created = client.post("/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": csrf}).json()

        # still draft -> cannot stop
        resp = client.post(f"/api/deployments/{created['id']}/stop", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 409

        client.post(f"/api/deployments/{created['id']}/deploy", headers={"X-CSRF-Token": csrf})
        stopped = client.post(f"/api/deployments/{created['id']}/stop", headers={"X-CSRF-Token": csrf})
        assert stopped.status_code == 200
        assert stopped.json()["status"] == "stopped"

    def test_download_before_deploy_returns_409(self, auth_client, monkeypatch):
        client, csrf = auth_client
        website_id = _create_completed_website(client, csrf, monkeypatch)
        created = client.post("/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": csrf}).json()

        resp = client.get(f"/api/deployments/{created['id']}/download")
        assert resp.status_code == 409

    def test_deleting_website_cleans_up_deployment_records(self, auth_client, monkeypatch):
        client, csrf = auth_client
        website_id = _create_completed_website(client, csrf, monkeypatch)
        created = client.post("/api/deployments", json={"website_id": website_id}, headers={"X-CSRF-Token": csrf}).json()
        client.post(f"/api/deployments/{created['id']}/deploy", headers={"X-CSRF-Token": csrf})

        resp = client.delete(f"/api/websites/{website_id}", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 204
        # The deployment row is gone too (DB cascade) — no orphaned record.
        assert client.get(f"/api/deployments/{created['id']}").status_code == 404
