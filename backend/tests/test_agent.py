import json

from app.agents.classifier import CLASSIFIER_SYSTEM_PROMPT
from app.integrations.claude.base import ClaudeMessage, ClaudeProvider, ProviderStatus
from app.integrations.claude.errors import ProviderRequestError
from app.knowledge.sync_agent import _MERGE_SYSTEM_PROMPT, _NEW_NOTE_SYSTEM_PROMPT, _WORTHINESS_SYSTEM_PROMPT

_SYNC_AGENT_PROMPTS = {_WORTHINESS_SYSTEM_PROMPT, _MERGE_SYSTEM_PROMPT, _NEW_NOTE_SYSTEM_PROMPT}


class _FakeProvider(ClaudeProvider):
    """Deterministic stand-in for a real Claude API call, used to test the
    orchestrator/streaming/persistence pipeline without network access or
    a real API key.

    AgentMode.chat now runs a classification call (see
    app/agents/classifier.py) before the real answer call, so this fake
    transparently auto-answers any classification request with
    `classification` (defaulting to casual/english, i.e. the old
    "just answer normally" behavior) without consuming `chunks` — existing
    tests that don't care about routing don't need to change at all.
    Pass a different `classification` JSON string to test routing
    behavior specifically.

    Every successful chat-mode turn also runs the Knowledge Maintenance
    Agent (see app/knowledge/sync_agent.py) against the user's message
    AFTER the real answer — those calls are similarly special-cased here
    (defaulting worthy=false, i.e. "never sync") so they don't disturb
    `call_count`/`received_messages`/`received_system_prompt`, which every
    pre-existing test asserts reflects the real answer call specifically.
    Tests that want to exercise sync behavior should set
    `sync_worthiness`/`sync_merge_result`/`sync_new_note_content` and read
    `sync_calls` (a list of (system_prompt, message) tuples) instead."""

    def __init__(
        self,
        chunks: list[str],
        fail_after: int | None = None,
        classification: str = '{"intent": "casual", "language": "english"}',
        sync_worthiness: str = '{"worthy": false}',
        sync_merge_result: str = "SKIP",
        sync_new_note_content: str = "# Note\n\nContent.",
    ):
        self.chunks = chunks
        self.fail_after = fail_after
        self.classification = classification
        self.sync_worthiness = sync_worthiness
        self.sync_merge_result = sync_merge_result
        self.sync_new_note_content = sync_new_note_content
        self.sync_calls: list[tuple[str, str]] = []
        self.received_messages: list[ClaudeMessage] | None = None
        self.received_system_prompt: str | None = None
        self.call_count = 0

    def status(self) -> ProviderStatus:
        return ProviderStatus(configured=True, provider="fake", model="fake-model", detail="ok")

    async def stream(self, messages, system_prompt):
        if system_prompt == CLASSIFIER_SYSTEM_PROMPT:
            self.call_count += 1
            self.received_messages = messages
            self.received_system_prompt = system_prompt
            yield self.classification
            return
        if system_prompt in _SYNC_AGENT_PROMPTS:
            self.sync_calls.append((system_prompt, messages[-1].content))
            if system_prompt == _WORTHINESS_SYSTEM_PROMPT:
                yield self.sync_worthiness
            elif system_prompt == _MERGE_SYSTEM_PROMPT:
                yield self.sync_merge_result
            else:
                yield self.sync_new_note_content
            return
        self.call_count += 1
        self.received_messages = messages
        self.received_system_prompt = system_prompt
        for i, chunk in enumerate(self.chunks):
            if self.fail_after is not None and i == self.fail_after:
                raise ProviderRequestError("simulated upstream failure")
            yield chunk


def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


def _patch_provider(monkeypatch, provider):
    import app.api.agent.router as agent_router_module

    monkeypatch.setattr(agent_router_module, "get_claude_provider", lambda: provider)


class TestClaudeStatus:
    def test_status_unconfigured_by_default(self, client):
        resp = client.get("/api/agent/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is False
        assert body["provider"] == "anthropic"
        assert "ANTHROPIC_API_KEY" in body["detail"]


class TestConversations:
    def test_create_conversation(self, auth_client):
        client, csrf = auth_client
        resp = client.post("/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 201
        assert resp.json()["title"] == "New conversation"
        assert resp.json()["mode"] == "chat"

    def test_create_conversation_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post("/api/agent/conversations", json={"mode": "chat"})
        assert resp.status_code == 403

    def test_create_conversation_scoped_to_project(self, auth_client):
        client, csrf = auth_client
        project = client.post(
            "/api/projects", json={"name": "Agent Project"}, headers={"X-CSRF-Token": csrf}
        ).json()
        resp = client.post(
            "/api/agent/conversations",
            json={"mode": "project", "project_id": project["id"]},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201
        assert resp.json()["project_name"] == "Agent Project"

    def test_create_conversation_unowned_project_404(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/agent/conversations",
            json={"mode": "project", "project_id": "00000000-0000-0000-0000-000000000000"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 404

    def test_list_conversations_empty_for_new_user(self, auth_client):
        client, _csrf = auth_client
        resp = client.get("/api/agent/conversations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_conversation_includes_messages(self, auth_client):
        client, csrf = auth_client
        created = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()
        resp = client.get(f"/api/agent/conversations/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["messages"] == []

    def test_rename_conversation(self, auth_client):
        client, csrf = auth_client
        created = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()
        resp = client.patch(
            f"/api/agent/conversations/{created['id']}",
            json={"title": "Renamed"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Renamed"

    def test_delete_conversation(self, auth_client):
        client, csrf = auth_client
        created = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()
        resp = client.delete(f"/api/agent/conversations/{created['id']}", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200
        assert client.get(f"/api/agent/conversations/{created['id']}").status_code == 404

    def test_conversations_require_authentication(self, client):
        resp = client.get("/api/agent/conversations")
        assert resp.status_code == 401

    def test_conversation_ownership_isolation(self, auth_client, client, email_outbox):
        owner_client, owner_csrf = auth_client
        owned = owner_client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": owner_csrf}
        ).json()

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

        assert client.get(f"/api/agent/conversations/{owned['id']}").status_code == 404


class TestSendMessage:
    def test_send_message_returns_503_when_unconfigured(self, auth_client):
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()
        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Hello"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 503
        assert "ANTHROPIC_API_KEY" in resp.json()["detail"]

    def test_send_message_persists_user_text_even_when_unconfigured(self, auth_client):
        """Regression test: a user's message must never silently disappear
        just because Claude isn't configured — it must still be there after
        the conversation is reloaded (e.g. on page refresh)."""
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()
        client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Help me draft a project plan"},
            headers={"X-CSRF-Token": csrf},
        )

        detail = client.get(f"/api/agent/conversations/{conv['id']}").json()
        assert len(detail["messages"]) == 2
        assert detail["messages"][0]["role"] == "user"
        assert detail["messages"][0]["content"] == "Help me draft a project plan"
        assert detail["messages"][1]["role"] == "assistant"
        assert detail["messages"][1]["error"] is not None
        assert detail["title"] == "Help me draft a project plan"

        history = client.get("/api/history").json()
        assert history["total"] == 1
        assert history["items"][0]["status"] == "failed"

    def test_send_message_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": _csrf}
        ).json()
        resp = client.post(f"/api/agent/conversations/{conv['id']}/messages", json={"content": "Hello"})
        assert resp.status_code == 403

    def test_send_message_streams_and_persists_with_configured_provider(self, auth_client, monkeypatch):
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()

        fake = _FakeProvider(chunks=["Hello", ", ", "world!"])
        _patch_provider(monkeypatch, fake)

        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Say hello"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        deltas = [e["text"] for e in events if e["type"] == "delta"]
        assert deltas == ["Hello", ", ", "world!"]
        assert events[-1]["type"] == "done"

        detail = client.get(f"/api/agent/conversations/{conv['id']}").json()
        assert len(detail["messages"]) == 2
        assert detail["messages"][0]["role"] == "user"
        assert detail["messages"][0]["content"] == "Say hello"
        assert detail["messages"][1]["role"] == "assistant"
        assert detail["messages"][1]["content"] == "Hello, world!"
        # First message auto-titles the conversation.
        assert detail["title"] == "Say hello"

    def test_send_message_injects_project_context_into_system_prompt(self, auth_client, monkeypatch):
        client, csrf = auth_client
        project = client.post(
            "/api/projects",
            json={"name": "Manufacturing HRMS", "description": "Factory HR system"},
            headers={"X-CSRF-Token": csrf},
        ).json()
        conv = client.post(
            "/api/agent/conversations",
            json={"mode": "project", "project_id": project["id"]},
            headers={"X-CSRF-Token": csrf},
        ).json()

        fake = _FakeProvider(chunks=["OK"])
        _patch_provider(monkeypatch, fake)

        client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "What is this project about?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert "Manufacturing HRMS" in fake.received_system_prompt
        assert "Factory HR system" in fake.received_system_prompt

    def test_send_message_injects_project_activity_into_system_prompt(self, auth_client, monkeypatch):
        client, csrf = auth_client
        project = client.post(
            "/api/projects",
            json={"name": "Manufacturing HRMS"},
            headers={"X-CSRF-Token": csrf},
        ).json()

        # A structured Word document requires no AI provider, so it's a
        # deterministic way to give the project real HistoryEntry activity.
        client.post(
            "/api/generation/document/word",
            json={
                "title": "Onboarding Guide",
                "project_id": project["id"],
                "blocks": [{"type": "paragraph", "text": "Welcome."}],
            },
            headers={"X-CSRF-Token": csrf},
        )

        conv = client.post(
            "/api/agent/conversations",
            json={"mode": "project", "project_id": project["id"]},
            headers={"X-CSRF-Token": csrf},
        ).json()

        fake = _FakeProvider(chunks=["OK"])
        _patch_provider(monkeypatch, fake)

        client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "What's happened in this project so far?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert "Recent activity in this project" in fake.received_system_prompt
        assert "Onboarding Guide" in fake.received_system_prompt
        assert "[document]" in fake.received_system_prompt

    def test_project_activity_context_excludes_other_users_projects(self, auth_client, client, email_outbox, monkeypatch):
        import re

        client_a, csrf_a = auth_client
        project = client_a.post(
            "/api/projects", json={"name": "User A's project"}, headers={"X-CSRF-Token": csrf_a}
        ).json()
        client_a.post(
            "/api/generation/document/word",
            json={
                "title": "Confidential Plan",
                "project_id": project["id"],
                "blocks": [{"type": "paragraph", "text": "Secret."}],
            },
            headers={"X-CSRF-Token": csrf_a},
        )

        second_password = "Str0ng!Passw0rd2"
        client.post(
            "/api/auth/signup",
            json={
                "full_name": "User B",
                "email": "userb@example.com",
                "password": second_password,
                "confirm_password": second_password,
                "accept_terms": True,
            },
        )
        token = re.search(r"token=([A-Za-z0-9_\-]+)", email_outbox[-1].text_body).group(1)
        client.post("/api/auth/verify-email", json={"token": token})
        login_resp = client.post("/api/auth/login", json={"email": "userb@example.com", "password": second_password})
        csrf_b = login_resp.cookies["aiagent_csrf"]

        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf_b}
        ).json()

        fake = _FakeProvider(chunks=["OK"])
        _patch_provider(monkeypatch, fake)

        client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Hello"},
            headers={"X-CSRF-Token": csrf_b},
        )
        assert "Confidential Plan" not in fake.received_system_prompt

    def test_send_message_creates_history_entry(self, auth_client, monkeypatch):
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()
        _patch_provider(monkeypatch, _FakeProvider(chunks=["Hi!"]))

        client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Hello agent"},
            headers={"X-CSRF-Token": csrf},
        )

        history = client.get("/api/history").json()
        assert history["total"] == 1
        assert history["items"][0]["type"] == "chat"
        assert history["items"][0]["status"] == "completed"

    def test_send_message_provider_failure_persists_error_and_failed_history(self, auth_client, monkeypatch):
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()
        fake = _FakeProvider(chunks=["Partial", " reply", " never finishes"], fail_after=1)
        _patch_provider(monkeypatch, fake)

        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Trigger a failure"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        assert events[-1]["type"] == "error"

        detail = client.get(f"/api/agent/conversations/{conv['id']}").json()
        assert len(detail["messages"]) == 2
        assistant_message = detail["messages"][1]
        assert assistant_message["content"] == "Partial"
        assert assistant_message["error"] is not None

        history = client.get("/api/history").json()
        assert history["items"][0]["status"] == "failed"

    def test_second_message_does_not_overwrite_title(self, auth_client, monkeypatch):
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()
        _patch_provider(monkeypatch, _FakeProvider(chunks=["First reply"]))
        client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "First message"},
            headers={"X-CSRF-Token": csrf},
        )
        _patch_provider(monkeypatch, _FakeProvider(chunks=["Second reply"]))
        client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Second message"},
            headers={"X-CSRF-Token": csrf},
        )
        detail = client.get(f"/api/agent/conversations/{conv['id']}").json()
        assert detail["title"] == "First message"
        assert len(detail["messages"]) == 4

    def test_send_message_to_unowned_conversation_404(self, auth_client, client, email_outbox):
        owner_client, owner_csrf = auth_client
        conv = owner_client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": owner_csrf}
        ).json()

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
        login_resp = client.post(
            "/api/auth/login", json={"email": "second@example.com", "password": second_password}
        )
        second_csrf = login_resp.cookies["aiagent_csrf"]

        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Hello"},
            headers={"X-CSRF-Token": second_csrf},
        )
        assert resp.status_code == 404


class TestChatRouting:
    """AgentMode.chat's routing layer (app/agents/classifier.py +
    orchestrator.run_chat_turn): casual messages go straight to Claude's
    normal persona; technical/knowledge messages are forced through a
    strict grounded-RAG persona that may only answer from the user's
    Obsidian vault. Every other mode's existing behavior must stay
    completely untouched (see test_non_chat_modes_are_not_classified)."""

    def test_casual_message_skips_vault_search_entirely(self, auth_client, monkeypatch):
        import app.agents.orchestrator as orchestrator_module

        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()

        def _fail_if_called(user_id):
            raise AssertionError("Vault search must not run for a casual message.")

        monkeypatch.setattr(orchestrator_module, "get_obsidian_provider", _fail_if_called)

        fake = _FakeProvider(chunks=["Hi there!"])
        _patch_provider(monkeypatch, fake)

        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Hi"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        route_event = next(e for e in events if e["type"] == "route")
        assert route_event["intent"] == "casual"
        assert route_event["sources"] == []
        assert fake.call_count == 2  # classify, then answer
        assert "grounded knowledge-base answer" not in fake.received_system_prompt

    def test_technical_message_grounds_answer_in_matching_note(self, auth_client, monkeypatch):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes",
            json={
                "path": "HRMS Payroll Requirements.md",
                "content": "The HRMS payroll module must support monthly salary runs and statutory deductions.",
            },
            headers={"X-CSRF-Token": csrf},
        )
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()

        fake = _FakeProvider(
            chunks=["Based on your notes, payroll needs monthly runs."],
            classification='{"intent": "technical", "language": "english"}',
        )
        _patch_provider(monkeypatch, fake)

        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "What are the HRMS payroll requirements?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        route_event = next(e for e in events if e["type"] == "route")
        assert route_event["intent"] == "technical"
        assert route_event["sources"]
        assert route_event["sources"][0]["title"] == "HRMS Payroll Requirements"

        assert fake.call_count == 2
        assert "grounded knowledge-base answer" in fake.received_system_prompt
        assert "ONLY source of truth" in fake.received_system_prompt
        assert "HRMS Payroll Requirements" in fake.received_system_prompt
        assert "statutory deductions" in fake.received_system_prompt

    def test_technical_message_with_no_matching_notes_instructs_honest_not_found(self, auth_client, monkeypatch):
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()

        fake = _FakeProvider(
            chunks=["I couldn't find this information in your knowledge base."],
            classification='{"intent": "technical", "language": "english"}',
        )
        _patch_provider(monkeypatch, fake)

        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "What is RAG?"},
            headers={"X-CSRF-Token": csrf},
        )
        events = _parse_sse(resp.text)
        route_event = next(e for e in events if e["type"] == "route")
        assert route_event["sources"] == []
        assert "no matching notes were found" in fake.received_system_prompt
        assert "MUST tell the user you couldn't find" in fake.received_system_prompt
        assert "do not answer from your own general knowledge" in fake.received_system_prompt

    def test_technical_message_when_vault_unavailable(self, auth_client, monkeypatch):
        import app.agents.orchestrator as orchestrator_module

        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()

        def _broken_provider(user_id):
            raise RuntimeError("vault is unreachable")

        monkeypatch.setattr(orchestrator_module, "get_obsidian_provider", _broken_provider)

        fake = _FakeProvider(
            chunks=["I could not search your knowledge base right now."],
            classification='{"intent": "technical", "language": "english"}',
        )
        _patch_provider(monkeypatch, fake)

        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Explain MCP"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert "unavailable right now" in fake.received_system_prompt
        assert "do not answer from your own general knowledge" in fake.received_system_prompt

    def test_casual_message_in_tamil_gets_language_adaptation_instruction(self, auth_client, monkeypatch):
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()

        fake = _FakeProvider(
            chunks=["வணக்கம்!"],
            classification='{"intent": "casual", "language": "tamil"}',
        )
        _patch_provider(monkeypatch, fake)

        client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "வணக்கம், எப்படி இருக்கீங்க?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert "Tamil" in fake.received_system_prompt
        assert "grounded knowledge-base answer" not in fake.received_system_prompt

    def test_non_chat_modes_are_not_classified(self, auth_client, monkeypatch):
        """Knowledge/Research/Project/etc. keep their exact pre-existing
        behavior — no classification call, no change to their own vault-
        search/grounding logic."""
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "project"}, headers={"X-CSRF-Token": csrf}
        ).json()

        fake = _FakeProvider(chunks=["OK"])
        _patch_provider(monkeypatch, fake)

        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "What is RAG?"},
            headers={"X-CSRF-Token": csrf},
        )
        events = _parse_sse(resp.text)
        assert not any(e["type"] == "route" for e in events)
        assert fake.call_count == 1

    def test_second_message_in_same_conversation_still_classifies(self, auth_client, monkeypatch):
        """Routing runs on every turn, not just the first."""
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()

        _patch_provider(monkeypatch, _FakeProvider(chunks=["Hi!"]))
        client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Hi"},
            headers={"X-CSRF-Token": csrf},
        )

        fake2 = _FakeProvider(
            chunks=["Grounded answer."],
            classification='{"intent": "technical", "language": "english"}',
        )
        _patch_provider(monkeypatch, fake2)
        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "What is MCP?"},
            headers={"X-CSRF-Token": csrf},
        )
        events = _parse_sse(resp.text)
        route_event = next(e for e in events if e["type"] == "route")
        assert route_event["intent"] == "technical"


class TestKnowledgeSyncWiring:
    """The Knowledge Maintenance Agent (app/knowledge/sync_agent.py) runs
    automatically after every chat-mode turn, additive to (never replacing)
    the Casual->Claude / Technical->Obsidian routing tested above."""

    def test_worthy_message_emits_sync_events_and_creates_note(self, auth_client, monkeypatch):
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()

        fake = _FakeProvider(
            chunks=["Got it, I'll remember that."],
            sync_worthiness='{"worthy": true, "topic": "Manufacturing HRMS", "summary": "Payroll must run monthly."}',
            sync_new_note_content="# Manufacturing HRMS\n\nPayroll must run monthly.",
        )
        _patch_provider(monkeypatch, fake)

        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "For this project, the HRMS payroll module must run monthly, not weekly."},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        sync_events = [e for e in events if e["type"] == "sync"]
        assert [e["phase"] for e in sync_events] == ["start", "done"]
        assert sync_events[1]["result"] == "created"
        assert sync_events[1]["topic"] == "Manufacturing HRMS"

        history = client.get("/api/knowledge/sync-history").json()
        assert len(history) == 1
        assert history[0]["action"] == "created"
        assert history[0]["topic"] == "Manufacturing HRMS"

        notes = client.get("/api/obsidian/notes").json()
        assert any(n["title"] == "Manufacturing HRMS" for n in notes)

    def test_casual_message_never_triggers_sync(self, auth_client, monkeypatch):
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()

        fake = _FakeProvider(chunks=["Hi there!"])  # default sync_worthiness is worthy=false
        _patch_provider(monkeypatch, fake)

        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Hi, how are you?"},
            headers={"X-CSRF-Token": csrf},
        )
        events = _parse_sse(resp.text)
        assert not any(e["type"] == "sync" for e in events)
        assert client.get("/api/knowledge/sync-history").json() == []

    def test_non_chat_mode_never_triggers_sync(self, auth_client, monkeypatch):
        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "project"}, headers={"X-CSRF-Token": csrf}
        ).json()

        fake = _FakeProvider(
            chunks=["OK"],
            sync_worthiness='{"worthy": true, "topic": "Should never run", "summary": "n/a"}',
        )
        _patch_provider(monkeypatch, fake)

        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Some project message that would otherwise be worthy."},
            headers={"X-CSRF-Token": csrf},
        )
        events = _parse_sse(resp.text)
        assert not any(e["type"] == "sync" for e in events)
        assert fake.sync_calls == []
        assert client.get("/api/knowledge/sync-history").json() == []

    def test_sync_failure_reports_unavailable_without_breaking_chat_reply(self, auth_client, monkeypatch):
        import app.agents.orchestrator as orchestrator_module

        client, csrf = auth_client
        conv = client.post(
            "/api/agent/conversations", json={"mode": "chat"}, headers={"X-CSRF-Token": csrf}
        ).json()

        def _broken_provider(user_id):
            raise RuntimeError("vault is unreachable")

        monkeypatch.setattr(orchestrator_module, "get_obsidian_provider", _broken_provider)

        fake = _FakeProvider(chunks=["Sure, no problem."])
        _patch_provider(monkeypatch, fake)

        resp = client.post(
            f"/api/agent/conversations/{conv['id']}/messages",
            json={"content": "Hi"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        # The chat reply itself must still succeed even though the vault
        # (and therefore any sync) is unreachable -- and since the vault
        # provider itself couldn't even be constructed, no sync is
        # attempted at all (no worthiness call was possible).
        assert any(e["type"] == "delta" for e in events)
        assert not any(e["type"] == "sync" for e in events)
