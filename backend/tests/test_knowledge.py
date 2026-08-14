import os
import time
from pathlib import Path

import pytest

from app.integrations.claude.base import ClaudeProvider, ProviderStatus
from app.integrations.claude.errors import ProviderRequestError
from app.integrations.obsidian.local_vault_provider import LocalVaultProvider, provision_vault
from app.knowledge.vault_analysis import (
    _analyzable_notes,
    analyze_vault,
    build_knowledge_graph,
    compute_health_score,
    find_broken_links,
    find_duplicates,
    find_orphan_notes,
    find_outdated,
)


# ---------------------------------------------------------------------------
# Deterministic vault analysis (no LLM, no network)
# ---------------------------------------------------------------------------


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    provision_vault(root)
    return LocalVaultProvider(root)


def _backdate(root: Path, rel_path: str, days: int) -> None:
    target = (root / rel_path).resolve()
    stamp = time.time() - days * 86400
    os.utime(target, (stamp, stamp))


class TestVaultAnalysis:
    def test_empty_vault_excludes_system_folder(self, vault):
        analysis = analyze_vault(vault)
        assert analysis.note_count == 0
        assert analysis.health_score == 100

    def test_find_duplicates_identical_title(self, vault):
        vault.create_note("01-Knowledge/HRMS.md", "# HRMS\nEmployee module notes.")
        vault.create_note("01-Knowledge/HRMS Copy.md", "# HRMS\nEmployee module notes, copy.")
        analysis = analyze_vault(vault)
        assert len(analysis.duplicates) == 1
        assert analysis.duplicates[0].reason == "identical title"
        assert analysis.duplicates[0].similarity == 1.0

    def test_find_duplicates_similar_content(self, vault):
        vault.create_note(
            "01-Knowledge/Payroll Rules.md",
            "# Payroll Rules\nTax deduction rates, overtime calculation, bonus schedule for employees.",
        )
        vault.create_note(
            "01-Knowledge/Payroll Policy.md",
            "# Payroll Policy\nTax deduction rates, overtime calculation, bonus schedule for staff.",
        )
        summaries = _analyzable_notes(vault)
        dupes = find_duplicates(summaries)
        assert len(dupes) == 1
        assert dupes[0].reason in ("similar title", "similar content")

    def test_find_duplicates_ignores_unrelated_notes(self, vault):
        vault.create_note("01-Knowledge/Alpha.md", "# Alpha\nCompletely unrelated topic about gardening.")
        vault.create_note("01-Knowledge/Beta.md", "# Beta\nA totally different subject: astronomy.")
        assert find_duplicates(_analyzable_notes(vault)) == []

    def test_find_outdated(self, vault):
        vault.create_note("01-Knowledge/Fresh.md", "# Fresh\nRecently written.")
        vault.create_note("01-Knowledge/Stale.md", "# Stale\nWritten a long time ago.")
        _backdate(vault.root, "01-Knowledge/Stale.md", days=200)

        outdated = find_outdated(_analyzable_notes(vault))
        assert len(outdated) == 1
        assert outdated[0].title == "Stale"
        assert outdated[0].days_since_update >= 199

    def test_find_broken_links(self, vault):
        vault.create_note("01-Knowledge/Source.md", "# Source\nSee [[Missing Target]] for details.")
        broken = find_broken_links(_analyzable_notes(vault))
        assert len(broken) == 1
        assert broken[0].target_name == "Missing Target"

    def test_links_to_real_note_are_not_broken(self, vault):
        vault.create_note("01-Knowledge/Target.md", "# Target\nThe destination note.")
        vault.create_note("01-Knowledge/Source.md", "# Source\nSee [[Target]] for details.")
        assert find_broken_links(_analyzable_notes(vault)) == []

    def test_find_orphan_notes(self, vault):
        vault.create_note("01-Knowledge/A.md", "# A\nLinks to [[B]].")
        vault.create_note("01-Knowledge/B.md", "# B\nThe linked note.")
        vault.create_note("01-Knowledge/Lonely.md", "# Lonely\nNo links in or out.")

        orphans = find_orphan_notes(_analyzable_notes(vault))
        assert orphans == ["01-Knowledge/Lonely.md"]

    def test_compute_health_score_perfect_vault(self):
        assert compute_health_score(note_count=5, duplicates=[], outdated=[], broken_links=[], orphan_notes=[]) == 100

    def test_compute_health_score_zero_notes(self):
        assert compute_health_score(note_count=0, duplicates=[], outdated=[], broken_links=[], orphan_notes=[]) == 100

    def test_compute_health_score_penalizes_and_caps(self):
        # 10 duplicates * 4 = 40, capped at 25
        score = compute_health_score(
            note_count=10,
            duplicates=[object()] * 10,
            outdated=[],
            broken_links=[],
            orphan_notes=[],
        )
        assert score == 75

    def test_build_knowledge_graph_dedupes_bidirectional_edges(self, vault):
        vault.create_note("01-Knowledge/A.md", "# A\nSee [[B]].")
        vault.create_note("01-Knowledge/B.md", "# B\nSee [[A]] back.")
        graph = build_knowledge_graph(vault)
        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1  # A<->B collapses to a single edge

    def test_analyze_vault_excludes_00_system_notes(self, vault):
        # provision_vault already wrote 00-System/Welcome.md
        vault.create_note("01-Knowledge/Real.md", "# Real\nActual user content.")
        analysis = analyze_vault(vault)
        assert analysis.note_count == 1

    def test_get_metadata_returns_real_note_metadata_without_content(self, vault):
        vault.create_note("01-Knowledge/Tagged.md", "# Tagged\n#important See [[Other]].")
        meta = vault.get_metadata("01-Knowledge/Tagged.md")
        assert meta.title == "Tagged"
        assert meta.tags == ["important"]
        assert meta.links == ["Other"]
        assert meta.size_bytes > 0
        assert meta.created_at is not None
        assert meta.updated_at is not None


# ---------------------------------------------------------------------------
# Knowledge API
# ---------------------------------------------------------------------------


class TestKnowledgeHealthEndpoint:
    def test_requires_authentication(self, client):
        resp = client.get("/api/knowledge/health")
        assert resp.status_code == 401

    def test_empty_vault_returns_perfect_score(self, auth_client):
        client, _csrf = auth_client
        resp = client.get("/api/knowledge/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["note_count"] == 0  # only the excluded welcome note exists
        assert body["health_score"] == 100
        assert body["gaps_count"] == 0
        assert body["updates_count"] == 0

    def test_health_reflects_real_vault_state(self, auth_client):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/HRMS.md", "content": "# HRMS\nEmployee and payroll module. See [[Ghost Note]]."},
            headers={"X-CSRF-Token": csrf},
        )
        client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/HRMS Copy.md", "content": "# HRMS\nDuplicate employee and payroll module."},
            headers={"X-CSRF-Token": csrf},
        )
        client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/Lonely.md", "content": "# Lonely\nStands alone."},
            headers={"X-CSRF-Token": csrf},
        )

        resp = client.get("/api/knowledge/health")
        body = resp.json()
        assert body["note_count"] == 3
        assert len(body["duplicates"]) == 1
        assert len(body["broken_links"]) == 1
        assert body["broken_links"][0]["target_name"] == "Ghost Note"
        assert "01-Knowledge/Lonely.md" in body["orphan_notes"]
        assert body["health_score"] < 100
        assert body["updates_count"] == 3  # three note creations logged


class TestKnowledgeGraphEndpoint:
    def test_requires_authentication(self, client):
        resp = client.get("/api/knowledge/graph")
        assert resp.status_code == 401

    def test_graph_reflects_links(self, auth_client):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/A.md", "content": "# A\nSee [[B]]."},
            headers={"X-CSRF-Token": csrf},
        )
        client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/B.md", "content": "# B\nDestination note."},
            headers={"X-CSRF-Token": csrf},
        )
        resp = client.get("/api/knowledge/graph")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["nodes"]) == 2
        assert len(body["edges"]) == 1


class TestKnowledgeUpdatesHistory:
    def test_note_mutations_are_logged_as_knowledge_updates(self, auth_client):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/Note.md", "content": "# Note\nOriginal."},
            headers={"X-CSRF-Token": csrf},
        )
        client.put(
            "/api/obsidian/notes/01-Knowledge/Note.md",
            json={"content": "# Note\nUpdated."},
            headers={"X-CSRF-Token": csrf},
        )
        client.delete(
            "/api/obsidian/notes/01-Knowledge/Note.md",
            headers={"X-CSRF-Token": csrf},
        )

        resp = client.get("/api/history?type=knowledge_update")
        assert resp.status_code == 200
        entries = resp.json()["items"]
        titles = [e["title"] for e in entries]
        assert any("Created note" in t for t in titles)
        assert any("Updated note" in t for t in titles)
        assert any("Deleted note" in t for t in titles)


class _FakeGapProvider(ClaudeProvider):
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


_SAMPLE_RESPONSE = """EXISTING:
- Basic employee records module

MISSING:
- Leave management workflow
- Shift scheduling

RECOMMENDED:
- Create a note on leave policy
- Create a note on shift patterns

DUPLICATES:
- None.

OUTDATED:
- None.
"""


def _patch_gap_provider(monkeypatch, provider):
    import app.api.knowledge.router as knowledge_router_module

    monkeypatch.setattr(knowledge_router_module, "get_claude_provider", lambda: provider)


class TestGapAnalysisEndpoint:
    def test_requires_authentication(self, client):
        resp = client.post("/api/knowledge/gaps", json={"query": "what am I missing?"})
        assert resp.status_code == 401

    def test_requires_csrf(self, auth_client):
        client, _csrf = auth_client
        resp = client.post("/api/knowledge/gaps", json={"query": "what am I missing?"})
        assert resp.status_code == 403

    def test_query_too_short_rejected(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/knowledge/gaps", json={"query": "hi"}, headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 422

    def test_unconfigured_provider_persists_query_and_returns_503(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/knowledge/gaps",
            json={"query": "What am I missing for a manufacturing HRMS?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 503

        listing = client.get("/api/knowledge/gaps")
        assert listing.status_code == 200
        analyses = listing.json()
        assert len(analyses) == 1
        assert analyses[0]["status"] == "failed"
        assert analyses[0]["query"] == "What am I missing for a manufacturing HRMS?"
        assert analyses[0]["error"]

    def test_configured_provider_persists_completed_analysis(self, auth_client, monkeypatch):
        client, csrf = auth_client
        fake = _FakeGapProvider(_SAMPLE_RESPONSE)
        _patch_gap_provider(monkeypatch, fake)

        resp = client.post(
            "/api/knowledge/gaps",
            json={"query": "What am I missing for a manufacturing HRMS?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "completed"
        assert "Leave management workflow" in body["missing_items"]
        assert "Shift scheduling" in body["missing_items"]
        assert "Create a note on leave policy" in body["recommended_additions"]
        assert body["duplicate_notes"] == []
        assert body["outdated_notes"] == []
        assert "Basic employee records module" in body["existing_summary"]

        get_resp = client.get(f"/api/knowledge/gaps/{body['id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == body["id"]

    def test_configured_provider_failure_persists_failed_analysis(self, auth_client, monkeypatch):
        client, csrf = auth_client
        fake = _FakeGapProvider(text="", fail=True)
        _patch_gap_provider(monkeypatch, fake)

        resp = client.post(
            "/api/knowledge/gaps",
            json={"query": "What am I missing for a manufacturing HRMS?"},
            headers={"X-CSRF-Token": csrf},
        )
        # in-stream failures are recorded and returned as a normal (failed-status) resource,
        # not surfaced as an HTTP error, since the query itself was successfully persisted.
        assert resp.status_code == 201
        assert resp.json()["status"] == "failed"

    def test_gap_analysis_includes_related_vault_notes_in_context(self, auth_client, monkeypatch):
        client, csrf = auth_client
        client.post(
            "/api/obsidian/notes",
            json={"path": "01-Knowledge/HRMS.md", "content": "# HRMS\nEmployee records and manufacturing HRMS basics."},
            headers={"X-CSRF-Token": csrf},
        )
        fake = _FakeGapProvider(_SAMPLE_RESPONSE)
        _patch_gap_provider(monkeypatch, fake)

        client.post(
            "/api/knowledge/gaps",
            json={"query": "manufacturing HRMS"},
            headers={"X-CSRF-Token": csrf},
        )
        assert fake.received_messages is not None
        assert "HRMS" in fake.received_messages[0].content

    def test_get_nonexistent_analysis_returns_404(self, auth_client):
        client, _csrf = auth_client
        resp = client.get("/api/knowledge/gaps/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_gap_analysis_with_invalid_project_returns_404(self, auth_client):
        client, csrf = auth_client
        resp = client.post(
            "/api/knowledge/gaps",
            json={"query": "what should this project cover?", "project_id": "00000000-0000-0000-0000-000000000000"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 404
