"""A genuine multi-module end-to-end journey test — the Phase 10 audit
found every existing test starts from the `auth_client` fixture shortcut
(a user is signed up, verified, and logged in before the test body ever
runs). Nothing in the suite exercised a real user's actual path through
the app: signup -> verify email -> login -> create a project -> generate
a document into it -> see it show up in project-scoped history -> chat
about the project and have the AI's context genuinely include that
document. Each step here re-uses the app's own real endpoints, not
fixture shortcuts, and each assertion checks that the *previous* step's
data is what powers the *next* step, not just that each endpoint
independently returns 2xx."""
import re

from app.integrations.claude.base import ClaudeMessage, ClaudeProvider, ProviderStatus


class _FakeProvider(ClaudeProvider):
    def __init__(self, chunks: list[str]):
        self.chunks = chunks
        self.received_system_prompt: str | None = None

    def status(self) -> ProviderStatus:
        return ProviderStatus(configured=True, provider="fake", model="fake-model", detail="ok")

    async def stream(self, messages, system_prompt):
        self.received_system_prompt = system_prompt
        for chunk in self.chunks:
            yield chunk


def test_signup_to_project_document_history_and_grounded_chat(client, email_outbox, monkeypatch):
    email = "journey@example.com"
    password = "Str0ng!Passw0rd"

    # 1. Signup — a real call, not the auth_client fixture shortcut.
    signup_resp = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Journey User",
            "email": email,
            "password": password,
            "confirm_password": password,
            "accept_terms": True,
        },
    )
    assert signup_resp.status_code == 201

    # 2. The account is unverified until the emailed token is used.
    token = re.search(r"token=([A-Za-z0-9_\-]+)", email_outbox[-1].text_body).group(1)
    verify_resp = client.post("/api/auth/verify-email", json={"token": token})
    assert verify_resp.status_code == 200

    # 3. Login establishes the real session + CSRF cookies used from here on.
    login_resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200
    csrf = login_resp.cookies["aiagent_csrf"]

    # 4. Create a project.
    project_resp = client.post(
        "/api/projects",
        json={"name": "Journey HRMS", "description": "End-to-end test project"},
        headers={"X-CSRF-Token": csrf},
    )
    assert project_resp.status_code == 201
    project = project_resp.json()

    # 5. Generate a real (structured, non-AI) document into that project.
    doc_resp = client.post(
        "/api/generation/document/word",
        json={
            "title": "Journey Onboarding Guide",
            "project_id": project["id"],
            "blocks": [{"type": "paragraph", "text": "Welcome to the journey test."}],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert doc_resp.status_code == 201
    document = doc_resp.json()
    assert document["project_id"] == project["id"]

    # 6. The document must be downloadable — proves storage actually wrote
    # real bytes, not just a DB row. Structured word/ppt/excel documents
    # are Document rows (like AI-drafted /api/documents), so they're
    # downloaded via /api/documents/{id}/download, not a generation route.
    download_resp = client.get(f"/api/documents/{document['id']}/download")
    assert download_resp.status_code == 200
    assert download_resp.content[:2] == b"PK"

    # 7. It must appear in project-scoped history, and NOT in another
    # project's history — proves History's project_id filter is real.
    scoped_history = client.get(f"/api/history?project_id={project['id']}")
    assert scoped_history.status_code == 200
    scoped_titles = [item["title"] for item in scoped_history.json()["items"]]
    assert any("Journey Onboarding Guide" in t for t in scoped_titles)

    other_project = client.post(
        "/api/projects", json={"name": "Unrelated Project"}, headers={"X-CSRF-Token": csrf}
    ).json()
    other_history = client.get(f"/api/history?project_id={other_project['id']}")
    assert other_history.json()["items"] == []

    # 8. Chat about the project (mode=project) and confirm the AI's system
    # prompt genuinely includes the project's real activity — the whole
    # point of project-scoped chat, not just that a conversation was created.
    conv_resp = client.post(
        "/api/agent/conversations",
        json={"mode": "project", "project_id": project["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert conv_resp.status_code == 201
    conversation = conv_resp.json()

    fake_provider = _FakeProvider(chunks=["Here's a summary of your project."])
    import app.api.agent.router as agent_router_module

    monkeypatch.setattr(agent_router_module, "get_claude_provider", lambda: fake_provider)

    message_resp = client.post(
        f"/api/agent/conversations/{conversation['id']}/messages",
        json={"content": "What has happened in this project so far?"},
        headers={"X-CSRF-Token": csrf},
    )
    assert message_resp.status_code == 200
    assert "Journey HRMS" in fake_provider.received_system_prompt
    assert "Journey Onboarding Guide" in fake_provider.received_system_prompt

    # 9. And the chat reply itself is now part of this user's overall
    # history too, alongside the earlier document.
    full_history = client.get("/api/history")
    assert full_history.json()["total"] >= 2
