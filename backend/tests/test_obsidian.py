import uuid

from app.integrations.claude.base import ProviderStatus
from app.integrations.obsidian.factory import get_knowledge_provider, get_obsidian_provider
from app.integrations.obsidian.local_vault_provider import LocalVaultProvider


def test_get_knowledge_provider_is_an_alias_for_get_obsidian_provider():
    assert get_knowledge_provider is get_obsidian_provider


class TestObsidianVaultPathOverride:
    """OBSIDIAN_VAULT_PATH (app/core/config.py) lets a single-user
    deployment point directly at a real, already-existing Obsidian vault
    instead of the default per-user {obsidian_vault_root}/{user_id}/
    layout — added for the master task's Part 2 (correct Obsidian vault
    path). Default (unset) behavior must stay exactly as before, since
    the whole rest of this file's isolation tests assume it."""

    def test_default_unset_uses_per_user_nesting(self, tmp_path, monkeypatch):
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "obsidian_vault_root", str(tmp_path / "vaults"))
        monkeypatch.setattr(settings, "obsidian_vault_path", None)

        user_id = uuid.uuid4()
        provider = get_obsidian_provider(user_id)
        assert isinstance(provider, LocalVaultProvider)
        assert provider.root == (tmp_path / "vaults" / str(user_id)).resolve()

    def test_configured_override_ignores_per_user_nesting(self, tmp_path, monkeypatch):
        """Two different user ids must resolve to the SAME directory when
        the override is set — that's the whole point (a single real vault
        shared by whoever's on this backend, per the master task's
        explicit single-user-deployment intent)."""
        from app.core.config import get_settings

        settings = get_settings()
        real_vault = tmp_path / "My Real Obsidian Vault"
        monkeypatch.setattr(settings, "obsidian_vault_path", str(real_vault))

        provider_a = get_obsidian_provider(uuid.uuid4())
        provider_b = get_obsidian_provider(uuid.uuid4())
        assert provider_a.root == real_vault.resolve()
        assert provider_b.root == real_vault.resolve()

    def test_existing_vault_contents_are_never_overwritten(self, tmp_path, monkeypatch):
        """The core safety guarantee: pointing this at a real vault that
        already has the user's own notes must not run the welcome-note/
        folder-scaffolding provisioning over it — provisioning is
        skipped entirely whenever the directory already exists."""
        from app.core.config import get_settings

        real_vault = tmp_path / "My Real Obsidian Vault"
        real_vault.mkdir()
        (real_vault / "My Existing Note.md").write_text("Content I already wrote by hand.")

        settings = get_settings()
        monkeypatch.setattr(settings, "obsidian_vault_path", str(real_vault))

        get_obsidian_provider(uuid.uuid4())

        assert (real_vault / "My Existing Note.md").read_text() == "Content I already wrote by hand."
        # None of the app's own scaffolding folders were created alongside it.
        assert not (real_vault / "00-System").exists()

    def test_missing_vault_path_is_provisioned_not_crashed(self, tmp_path, monkeypatch):
        """If OBSIDIAN_VAULT_PATH points at a directory that doesn't exist
        yet, the app must provision it (folder scaffolding + welcome
        note) rather than raising — matches the existing per-user
        behavior, just applied to the configured single path."""
        from app.core.config import get_settings

        target = tmp_path / "not-created-yet"
        settings = get_settings()
        monkeypatch.setattr(settings, "obsidian_vault_path", str(target))

        provider = get_obsidian_provider(uuid.uuid4())
        assert target.exists()
        assert (target / "00-System").exists()
        assert provider.root == target.resolve()


def test_status_auto_provisions_vault(auth_client):
    client, _csrf = auth_client
    resp = client.get("/api/obsidian/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["connected"] is True
    assert body["note_count"] == 1  # the welcome note
    assert "00-System" in body["folders"]
    assert "09-AI-Memory" in body["folders"]


def test_status_requires_authentication(client):
    resp = client.get("/api/obsidian/status")
    assert resp.status_code == 401


class TestNoteCrud:
    def test_create_note(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/AI/Agents.md", "content": "# AI Agents\n\nAbout #agents and [[Machine Learning]]."},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "AI Agents"
        assert body["tags"] == ["agents"]
        assert body["links"] == ["Machine Learning"]

    def test_create_note_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post("/api/obsidian/notes", json={"path": "a.md", "content": "x"})
        assert resp.status_code == 403

    def test_create_duplicate_note_rejected(self, auth_client):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes", json={"path": "a.md", "content": "x"}, headers={"X-CSRF-Token": csrf}
        )
        resp = client.post(
            "/api/obsidian/notes", json={"path": "a.md", "content": "y"}, headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 409

    def test_create_note_without_md_extension_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/obsidian/notes", json={"path": "a.txt", "content": "x"}, headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 400

    def test_create_note_path_traversal_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/obsidian/notes",
            json={"path": "../../../etc/passwd.md", "content": "x"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 400

    def test_read_note(self, auth_client):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/Note.md", "content": "# Note\n\nHello."},
            headers={"X-CSRF-Token": csrf},
        )
        resp = client.get("/api/obsidian/notes/01-Knowledge/Note.md")
        assert resp.status_code == 200
        assert resp.json()["content"] == "# Note\n\nHello."

    def test_read_missing_note_404(self, auth_client):
        client, _csrf = auth_client
        resp = client.get("/api/obsidian/notes/nonexistent.md")
        assert resp.status_code == 404

    def test_read_note_path_traversal_rejected(self, auth_client):
        client, _csrf = auth_client
        resp = client.get("/api/obsidian/notes/..%2F..%2F..%2Fetc%2Fpasswd.md")
        assert resp.status_code in (400, 404)

    def test_update_note(self, auth_client):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes", json={"path": "a.md", "content": "old"}, headers={"X-CSRF-Token": csrf}
        )
        resp = client.put(
            "/api/obsidian/notes/a.md", json={"content": "new content"}, headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "new content"

    def test_update_missing_note_404(self, auth_client):
        client, csrf = auth_client
        resp = client.put(
            "/api/obsidian/notes/missing.md", json={"content": "x"}, headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 404

    def test_append_creates_if_missing(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/obsidian/notes/new-note.md/append",
            json={"content": "First content"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "First content"

    def test_append_to_existing_note(self, auth_client):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes", json={"path": "a.md", "content": "line one"}, headers={"X-CSRF-Token": csrf}
        )
        resp = client.post(
            "/api/obsidian/notes/a.md/append", json={"content": "line two"}, headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 200
        assert "line one" in resp.json()["content"]
        assert "line two" in resp.json()["content"]

    def test_move_note(self, auth_client):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes", json={"path": "old.md", "content": "x"}, headers={"X-CSRF-Token": csrf}
        )
        resp = client.post(
            "/api/obsidian/notes/old.md/move", json={"new_path": "new.md"}, headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 200
        assert resp.json()["path"] == "new.md"
        assert client.get("/api/obsidian/notes/old.md").status_code == 404
        assert client.get("/api/obsidian/notes/new.md").status_code == 200

    def test_delete_note(self, auth_client):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes", json={"path": "a.md", "content": "x"}, headers={"X-CSRF-Token": csrf}
        )
        resp = client.delete("/api/obsidian/notes/a.md", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200
        assert client.get("/api/obsidian/notes/a.md").status_code == 404

    def test_delete_missing_note_404(self, auth_client):
        client, csrf = auth_client
        resp = client.delete("/api/obsidian/notes/missing.md", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 404


class TestListAndSearch:
    def test_list_notes_by_folder(self, auth_client):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/A.md", "content": "x"},
            headers={"X-CSRF-Token": csrf},
        )
        client.post(
            "/api/obsidian/notes",
            json={"path": "02-Projects/B.md", "content": "y"},
            headers={"X-CSRF-Token": csrf},
        )
        resp = client.get("/api/obsidian/notes", params={"folder": "01-Knowledge"})
        paths = [n["path"] for n in resp.json()]
        assert paths == ["01-Knowledge/A.md"]

    def test_search_matches_content_keywords(self, auth_client):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes",
            json={
                "path": "01-Knowledge/HRMS.md",
                "content": "# HRMS\n\nExisting features: Payroll, Attendance, Leave, Recruitment.",
            },
            headers={"X-CSRF-Token": csrf},
        )
        client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/Weather.md", "content": "# Weather\n\nIt might rain tomorrow."},
            headers={"X-CSRF-Token": csrf},
        )
        resp = client.get("/api/obsidian/notes", params={"search": "Tell me about our HRMS payroll setup"})
        paths = [n["path"] for n in resp.json()]
        assert paths == ["01-Knowledge/HRMS.md"]

    def test_search_no_match_returns_empty(self, auth_client):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes", json={"path": "a.md", "content": "unrelated content"},
            headers={"X-CSRF-Token": csrf},
        )
        resp = client.get("/api/obsidian/notes", params={"search": "xyzzy nonexistent topic"})
        assert resp.json() == []


def test_vault_isolation_between_users(auth_client, client, email_outbox):
    owner_client, owner_csrf = auth_client
    owner_client.post(
        "/api/obsidian/notes",
        json={"path": "01-Knowledge/Secret.md", "content": "owner's private note"},
        headers={"X-CSRF-Token": owner_csrf},
    )

    import re

    second_password = "Str0ng!Passw0rd"
    client.post(
        "/api/auth/signup",
        json={
            "full_name": "Second User",
            "email": "second@example.com",
            "password": second_password,
            "confirm_password": second_password,
            "accept_terms": True,
        },
    )
    token = re.search(r"token=([A-Za-z0-9_\-]+)", email_outbox[-1].text_body).group(1)
    client.post("/api/auth/verify-email", json={"token": token})
    client.post("/api/auth/login", json={"email": "second@example.com", "password": second_password})

    resp = client.get("/api/obsidian/notes")
    paths = [n["path"] for n in resp.json()]
    assert "01-Knowledge/Secret.md" not in paths

    assert client.get("/api/obsidian/notes/01-Knowledge/Secret.md").status_code == 404


def _signup_and_login_second_user(client, email_outbox, email="second-write@example.com"):
    import re

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


class TestWriteOperationIsolationBetweenUsers:
    """The Phase 10 audit found test_vault_isolation_between_users above
    only exercises read/list isolation — update/move/delete on a path
    that lives in the owner's vault, attempted from a second user's
    session, was never confirmed to 404 rather than mutating (or
    reaching into) the owner's vault. Each provider is scoped to
    get_obsidian_provider(user.id) (app/api/obsidian/router.py), so this
    also serves as regression coverage for that per-user scoping."""

    @staticmethod
    def _relogin_as_owner(client):
        """auth_client's client and this test's separately-injected `client`
        are the literal same TestClient/cookie-jar object (pytest fixture
        caching) — the second user's login below already overwrote the
        owner's session cookies in that shared jar, so the owner must
        re-login before any post-mutation check (see the identical pattern
        in test_history.py::test_history_entry_ownership_isolation)."""
        client.post("/api/auth/login", json={"email": "owner@example.com", "password": "Str0ng!Passw0rd"})

    def test_update_is_isolated(self, auth_client, client, email_outbox):
        owner_client, owner_csrf = auth_client
        owner_client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/Secret.md", "content": "owner's original content"},
            headers={"X-CSRF-Token": owner_csrf},
        )
        second_csrf = _signup_and_login_second_user(client, email_outbox, "second-update@example.com")

        resp = client.put(
            "/api/obsidian/notes/01-Knowledge/Secret.md",
            json={"content": "tampered by second user"},
            headers={"X-CSRF-Token": second_csrf},
        )
        assert resp.status_code == 404

        self._relogin_as_owner(client)
        owner_read = client.get("/api/obsidian/notes/01-Knowledge/Secret.md")
        assert owner_read.json()["content"] == "owner's original content"

    def test_move_is_isolated(self, auth_client, client, email_outbox):
        owner_client, owner_csrf = auth_client
        owner_client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/Secret.md", "content": "owner's note"},
            headers={"X-CSRF-Token": owner_csrf},
        )
        second_csrf = _signup_and_login_second_user(client, email_outbox, "second-move@example.com")

        resp = client.post(
            "/api/obsidian/notes/01-Knowledge/Secret.md/move",
            json={"new_path": "hijacked.md"},
            headers={"X-CSRF-Token": second_csrf},
        )
        assert resp.status_code == 404
        # The second user's own vault must not contain the hijacked path either.
        assert client.get("/api/obsidian/notes/hijacked.md").status_code == 404

        self._relogin_as_owner(client)
        assert client.get("/api/obsidian/notes/01-Knowledge/Secret.md").status_code == 200

    def test_delete_is_isolated(self, auth_client, client, email_outbox):
        owner_client, owner_csrf = auth_client
        owner_client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/Secret.md", "content": "owner's note"},
            headers={"X-CSRF-Token": owner_csrf},
        )
        second_csrf = _signup_and_login_second_user(client, email_outbox, "second-delete@example.com")

        resp = client.delete(
            "/api/obsidian/notes/01-Knowledge/Secret.md", headers={"X-CSRF-Token": second_csrf}
        )
        assert resp.status_code == 404

        self._relogin_as_owner(client)
        assert client.get("/api/obsidian/notes/01-Knowledge/Secret.md").status_code == 200

    def test_append_creates_in_second_users_own_vault_not_owners(self, auth_client, client, email_outbox):
        """append creates-if-missing by design (see test_append_creates_if_missing
        above) — confirms that when the path doesn't exist in the second
        user's own vault, it creates a new note there rather than ever
        touching the owner's note of the same path."""
        owner_client, owner_csrf = auth_client
        owner_client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/Secret.md", "content": "owner's original content"},
            headers={"X-CSRF-Token": owner_csrf},
        )
        second_csrf = _signup_and_login_second_user(client, email_outbox, "second-append@example.com")

        resp = client.post(
            "/api/obsidian/notes/01-Knowledge/Secret.md/append",
            json={"content": "second user's own new note"},
            headers={"X-CSRF-Token": second_csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "second user's own new note"

        self._relogin_as_owner(client)
        owner_read = client.get("/api/obsidian/notes/01-Knowledge/Secret.md")
        assert owner_read.json()["content"] == "owner's original content"


class TestAgentKnowledgeModeGrounding:
    def _fake_provider(self, chunks):
        class _FakeProvider:
            def status(self):
                return ProviderStatus(configured=True, provider="fake", model="fake-model", detail="ok")

            async def stream(self, messages, system_prompt):
                self.received_system_prompt = system_prompt
                for c in chunks:
                    yield c

        return _FakeProvider()

    def test_knowledge_mode_grounds_reply_in_matching_note(self, auth_client, monkeypatch):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes",
            json={
                "path": "01-Knowledge/HRMS.md",
                "content": "# HRMS\n\nExisting features: Payroll, Attendance, Leave, Recruitment.",
            },
            headers={"X-CSRF-Token": csrf},
        )
        conv = client.post(
            "/api/agent/conversations", json={"mode": "knowledge"}, headers={"X-CSRF-Token": csrf}
        ).json()

        import app.api.agent.router as agent_router_module

        fake = self._fake_provider(["Sure, here's what I found."])
        monkeypatch.setattr(agent_router_module, "get_claude_provider", lambda: fake)

        client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "What HRMS features do we already have?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert "HRMS" in fake.received_system_prompt
        assert "Payroll" in fake.received_system_prompt

    def test_knowledge_mode_honest_when_no_notes_match(self, auth_client, monkeypatch):
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "knowledge"}, headers={"X-CSRF-Token": csrf}
        ).json()

        import app.api.agent.router as agent_router_module

        fake = self._fake_provider(["I don't see anything about that."])
        monkeypatch.setattr(agent_router_module, "get_claude_provider", lambda: fake)

        client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "What do my notes say about quantum computing?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert "no matching notes were found" in fake.received_system_prompt

    def test_chat_mode_does_not_search_vault(self, auth_client, monkeypatch):
        """Chat mode is explicitly not a vault-search mode — confirms modes
        stay genuinely different, not vault-grounded across the board."""
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/HRMS.md", "content": "# HRMS\n\nPayroll info."},
            headers={"X-CSRF-Token": csrf},
        )
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()

        import app.api.agent.router as agent_router_module

        fake = self._fake_provider(["Hi!"])
        monkeypatch.setattr(agent_router_module, "get_claude_provider", lambda: fake)

        client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Tell me about HRMS payroll"},
            headers={"X-CSRF-Token": csrf},
        )
        # Chat mode's base prompt mentions "vault" only in the generic
        # honesty instruction shared by all modes — it must NOT contain an
        # actual vault-search context injection (which knowledge/research
        # modes get).
        assert "Vault search:" not in fake.received_system_prompt
        assert "Relevant notes from the user's Obsidian vault" not in fake.received_system_prompt
