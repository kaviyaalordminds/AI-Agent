"""CSRF-rejection coverage for every state-changing (POST/PATCH/DELETE)
endpoint that declares `Depends(require_csrf)`. Each of these was already
protected in code, but most had never been proven by a test that a
request without a valid X-CSRF-Token is actually rejected — see the
Phase 10 test-coverage audit. require_csrf (app/security/sessions.py)
only depends on the session, not on the target resource, so a
nonexistent resource id is safe to use here: the 403 must happen before
any resource lookup.

Also covers the one real bug the audit found: DELETE /api/documents/{id}
had no CSRF protection in code at all (now fixed in
app/api/documents/router.py).
"""
import uuid

_MISSING = uuid.uuid4()


class TestUsersCsrf:
    def test_update_me_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.patch("/api/users/me", json={"full_name": "New Name"})
        assert resp.status_code == 403

    def test_change_password_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post(
            "/api/users/me/change-password",
            json={"current_password": "x", "new_password": "NewStrong1!", "confirm_password": "NewStrong1!"},
        )
        assert resp.status_code == 403

    def test_change_email_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post(
            "/api/users/me/change-email", json={"new_email": "new@example.com", "current_password": "x"}
        )
        assert resp.status_code == 403

    def test_update_settings_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.patch("/api/users/me/settings", json={"theme": "dark"})
        assert resp.status_code == 403


class TestHistoryCsrf:
    def test_update_entry_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.patch(f"/api/history/{_MISSING}", json={"title": "New title"})
        assert resp.status_code == 403

    def test_delete_entry_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.delete(f"/api/history/{_MISSING}")
        assert resp.status_code == 403


class TestProjectsCsrf:
    def test_update_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.patch(f"/api/projects/{_MISSING}", json={"name": "New name"})
        assert resp.status_code == 403

    def test_archive_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post(f"/api/projects/{_MISSING}/archive")
        assert resp.status_code == 403

    def test_unarchive_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post(f"/api/projects/{_MISSING}/unarchive")
        assert resp.status_code == 403

    def test_duplicate_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post(f"/api/projects/{_MISSING}/duplicate")
        assert resp.status_code == 403

    def test_delete_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.delete(f"/api/projects/{_MISSING}")
        assert resp.status_code == 403


class TestObsidianCsrf:
    def test_update_note_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.put("/api/obsidian/notes/nonexistent.md", json={"content": "x"})
        assert resp.status_code == 403

    def test_append_note_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post("/api/obsidian/notes/nonexistent.md/append", json={"content": "x"})
        assert resp.status_code == 403

    def test_move_note_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post("/api/obsidian/notes/nonexistent.md/move", json={"new_path": "moved.md"})
        assert resp.status_code == 403

    def test_delete_note_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.delete("/api/obsidian/notes/nonexistent.md")
        assert resp.status_code == 403


class TestAgentCsrf:
    def test_rename_conversation_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.patch(f"/api/agent/conversations/{_MISSING}", json={"title": "New title"})
        assert resp.status_code == 403

    def test_delete_conversation_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.delete(f"/api/agent/conversations/{_MISSING}")
        assert resp.status_code == 403


class TestAuthSessionManagementCsrf:
    def test_logout_all_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post("/api/auth/logout-all")
        assert resp.status_code == 403

    def test_revoke_session_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.delete(f"/api/auth/sessions/{_MISSING}")
        assert resp.status_code == 403


class TestDocumentsCsrf:
    def test_delete_document_requires_csrf(self, auth_client):
        """Regression test: DELETE /api/documents/{id} had no CSRF
        protection at all until this was fixed (see
        app/api/documents/router.py) — found by the Phase 10 audit."""
        client, _csrf = auth_client
        resp = client.delete(f"/api/documents/{_MISSING}")
        assert resp.status_code == 403
