def test_bare_health_check_no_auth_required(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_api_health_check_no_auth_required(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "environment" in body


class TestCapabilitiesEndpoint:
    def test_requires_authentication(self, client):
        assert client.get("/api/system/capabilities").status_code == 401

    def test_reports_all_categories_with_real_status(self, auth_client):
        client, _csrf = auth_client
        resp = client.get("/api/system/capabilities")
        assert resp.status_code == 200
        body = resp.json()

        expected_categories = {
            "ai", "audio", "transcription", "voice", "image", "video",
            "documents", "obsidian", "storage", "deployment",
        }
        assert set(body.keys()) == expected_categories

        for category, capability in body.items():
            assert isinstance(capability["available"], bool), category
            assert capability["mode"] in ("local", "production"), category
            assert capability["provider"], category
            assert capability["reason"], category

    def test_ai_unconfigured_in_test_env_is_reported_honestly(self, auth_client):
        client, _csrf = auth_client
        body = client.get("/api/system/capabilities").json()
        # conftest.py pins AI_PROVIDER=anthropic with no ANTHROPIC_API_KEY.
        assert body["ai"]["available"] is False
        assert body["ai"]["provider"] == "anthropic"
        assert "ANTHROPIC_API_KEY" in body["ai"]["reason"]

    def test_documents_capability_tracks_ai_availability(self, auth_client):
        client, _csrf = auth_client
        body = client.get("/api/system/capabilities").json()
        assert body["documents"]["available"] == body["ai"]["available"]

    def test_obsidian_capability_reflects_this_users_own_vault(self, auth_client):
        client, _csrf = auth_client
        body = client.get("/api/system/capabilities").json()
        assert body["obsidian"]["available"] is True
        assert "vault" in body["obsidian"]["reason"].lower()

    def test_storage_capability_reports_writable_root(self, auth_client):
        client, _csrf = auth_client
        body = client.get("/api/system/capabilities").json()
        assert body["storage"]["available"] is True

    def test_deployment_capability_local_always_available(self, auth_client):
        client, _csrf = auth_client
        body = client.get("/api/system/capabilities").json()
        assert body["deployment"]["available"] is True
        assert body["deployment"]["provider"] == "local"


class TestProvidersHealthEndpoint:
    def test_requires_authentication(self, client):
        assert client.get("/api/system/providers/health").status_code == 401

    def test_reports_all_components(self, auth_client):
        client, _csrf = auth_client
        resp = client.get("/api/system/providers/health")
        assert resp.status_code == 200
        body = resp.json()

        expected_components = {"database", "ai_provider", "obsidian", "storage", "job_queue"}
        assert set(body.keys()) == expected_components
        for component, health in body.items():
            assert health["status"] in ("ok", "degraded", "down"), component
            assert health["detail"], component

    def test_database_is_ok_against_real_test_db(self, auth_client):
        client, _csrf = auth_client
        body = client.get("/api/system/providers/health").json()
        assert body["database"]["status"] == "ok"

    def test_never_exposes_secrets(self, auth_client, monkeypatch):
        client, _csrf = auth_client
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-super-secret-value-should-not-leak")
        body = client.get("/api/system/providers/health").json()
        raw_text = str(body)
        assert "sk-ant-super-secret-value-should-not-leak" not in raw_text

        cap_body = client.get("/api/system/capabilities").json()
        assert "sk-ant-super-secret-value-should-not-leak" not in str(cap_body)
