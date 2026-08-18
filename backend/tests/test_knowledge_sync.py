import uuid

import pytest

from app.integrations.obsidian.errors import InvalidNotePathError
from app.integrations.obsidian.local_vault_provider import LocalVaultProvider, validate_obsidian_path
from app.integrations.obsidian.vault_identity import verify_vault_id
from app.knowledge.sync_agent import (
    WorthinessResult,
    _choose_folder,
    _find_matching_note,
    apply_sync,
    assess_knowledge_worthiness,
)
from app.models.knowledge_sync import KnowledgeSyncAction


class _FakeCompleteProvider:
    """Minimal stand-in for ClaudeProvider — sync_agent only ever calls
    `complete()` (app/integrations/claude/utils.py), which itself only
    calls provider.stream(), so this is enough to drive it without pulling
    in the full test_agent.py fake."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)

    def status(self):
        raise NotImplementedError

    async def stream(self, messages, system_prompt):
        yield self._responses.pop(0)


class TestValidateObsidianPath:
    """The single backend-enforced guard against writing outside the
    configured vault (see local_vault_provider.py's docstring) — every
    Obsidian write anywhere in the app funnels through this, including the
    new Knowledge Maintenance Agent."""

    def test_rejects_parent_traversal(self, tmp_path):
        with pytest.raises(InvalidNotePathError):
            validate_obsidian_path(tmp_path, "../outside.md")

    def test_rejects_nested_traversal_to_project_folder(self, tmp_path):
        with pytest.raises(InvalidNotePathError):
            validate_obsidian_path(tmp_path, "../../AI-Agent/backend/notes.md")

    def test_rejects_absolute_windows_path(self, tmp_path):
        with pytest.raises(InvalidNotePathError):
            validate_obsidian_path(tmp_path, r"C:\xampp\htdocs\Lordminds\AI-Agent\knowledge\note.md")

    def test_rejects_absolute_posix_path(self, tmp_path):
        with pytest.raises(InvalidNotePathError):
            validate_obsidian_path(tmp_path, "/etc/passwd.md")

    def test_rejects_home_relative_path(self, tmp_path):
        with pytest.raises(InvalidNotePathError):
            validate_obsidian_path(tmp_path, "~/notes.md")

    def test_rejects_non_markdown_extension(self, tmp_path):
        with pytest.raises(InvalidNotePathError):
            validate_obsidian_path(tmp_path, "note.txt")

    def test_accepts_valid_relative_path(self, tmp_path):
        resolved = validate_obsidian_path(tmp_path, "01-Knowledge/RAG.md")
        assert resolved == (tmp_path / "01-Knowledge" / "RAG.md").resolve()


class TestVaultIdentity:
    def test_unverifiable_when_no_obsidian_app_config_present(self, tmp_path, monkeypatch):
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setattr("app.integrations.obsidian.vault_identity.Path.home", lambda: tmp_path / "nonexistent-home")
        result = verify_vault_id("some-vault-id", tmp_path)
        assert result.status == "unverifiable"

    def test_verified_when_config_matches(self, tmp_path):
        vault_path = tmp_path / "My Vault"
        vault_path.mkdir()
        config_dir = tmp_path / "obsidian-config"
        config_dir.mkdir()
        config_file = config_dir / "obsidian.json"
        config_file.write_text(
            '{"vaults": {"abc123": {"path": "%s"}}}' % str(vault_path).replace("\\", "\\\\")
        )

        result = verify_vault_id("abc123", vault_path)
        # locate_obsidian_app_config() looks at real OS locations, not
        # config_file directly -- so exercise the comparison logic via a
        # monkeypatched locator instead of relying on env-dependent paths.
        import app.integrations.obsidian.vault_identity as vault_identity_module

        original_locate = vault_identity_module.locate_obsidian_app_config
        vault_identity_module.locate_obsidian_app_config = lambda: config_file
        try:
            result = verify_vault_id("abc123", vault_path)
        finally:
            vault_identity_module.locate_obsidian_app_config = original_locate
        assert result.status == "verified"

    def test_mismatch_when_config_points_elsewhere(self, tmp_path):
        import app.integrations.obsidian.vault_identity as vault_identity_module

        vault_path = tmp_path / "My Vault"
        other_path = tmp_path / "Some Other Folder"
        config_file = tmp_path / "obsidian.json"
        config_file.write_text('{"vaults": {"abc123": {"path": "%s"}}}' % str(other_path).replace("\\", "\\\\"))

        original_locate = vault_identity_module.locate_obsidian_app_config
        vault_identity_module.locate_obsidian_app_config = lambda: config_file
        try:
            result = verify_vault_id("abc123", vault_path)
        finally:
            vault_identity_module.locate_obsidian_app_config = original_locate
        assert result.status == "mismatch"


class TestAssessKnowledgeWorthiness:
    pytestmark = pytest.mark.asyncio

    async def test_trivial_greeting_never_calls_claude(self):
        provider = _FakeCompleteProvider(responses=[])
        result = await assess_knowledge_worthiness(provider, "Hi")
        assert result.worthy is False

    async def test_thank_you_never_calls_claude(self):
        provider = _FakeCompleteProvider(responses=[])
        result = await assess_knowledge_worthiness(provider, "Thank you!")
        assert result.worthy is False

    async def test_short_message_never_calls_claude(self):
        provider = _FakeCompleteProvider(responses=[])
        result = await assess_knowledge_worthiness(provider, "ok cool")
        assert result.worthy is False

    async def test_worthy_message_parsed(self):
        provider = _FakeCompleteProvider(
            responses=['{"worthy": true, "topic": "HRMS Payroll", "summary": "Payroll must run monthly."}']
        )
        result = await assess_knowledge_worthiness(
            provider, "We decided the HRMS payroll module must run monthly, not weekly."
        )
        assert result.worthy is True
        assert result.topic == "HRMS Payroll"
        assert result.summary == "Payroll must run monthly."

    async def test_unparseable_response_defaults_to_not_worthy(self):
        provider = _FakeCompleteProvider(responses=["not json at all"])
        result = await assess_knowledge_worthiness(provider, "This is a long enough message to pass the filter.")
        assert result.worthy is False

    async def test_provider_failure_defaults_to_not_worthy(self):
        class _Broken:
            def status(self):
                raise NotImplementedError

            async def stream(self, messages, system_prompt):
                raise RuntimeError("boom")
                yield  # pragma: no cover

        result = await assess_knowledge_worthiness(_Broken(), "This is a long enough message to pass the filter.")
        assert result.worthy is False


class TestApplySync:
    pytestmark = pytest.mark.asyncio

    def _provider(self, tmp_path):
        return LocalVaultProvider(tmp_path / "vault")

    async def test_creates_new_note_when_no_match(self, tmp_path, db_session):
        from app.models.user import User

        user = User(email=f"{uuid.uuid4()}@example.com", password_hash="x", full_name="Test", email_verified=True)
        db_session.add(user)
        db_session.commit()

        provider = self._provider(tmp_path)
        claude = _FakeCompleteProvider(responses=["# Manufacturing HRMS\n\nMust support monthly payroll runs."])
        worthiness = WorthinessResult(worthy=True, topic="Manufacturing HRMS", summary="Must support monthly payroll runs.")

        row = await apply_sync(db_session, user, provider, claude, "chat", worthiness)

        assert row.action == KnowledgeSyncAction.created
        assert row.note_path is not None
        note = provider.read_note(row.note_path)
        assert "Manufacturing HRMS" in note.content

    async def test_updates_existing_note_on_new_info(self, tmp_path, db_session):
        from app.models.user import User

        user = User(email=f"{uuid.uuid4()}@example.com", password_hash="x", full_name="Test", email_verified=True)
        db_session.add(user)
        db_session.commit()

        provider = self._provider(tmp_path)
        provider.create_note("01-Knowledge/HRMS Payroll.md", "# HRMS Payroll\n\nSupports weekly runs.")

        claude = _FakeCompleteProvider(responses=["# HRMS Payroll\n\nSupports weekly and monthly runs."])
        worthiness = WorthinessResult(worthy=True, topic="HRMS Payroll", summary="Also supports monthly runs now.")

        row = await apply_sync(db_session, user, provider, claude, "chat", worthiness)

        assert row.action == KnowledgeSyncAction.updated
        assert row.note_path == "01-Knowledge/HRMS Payroll.md"
        note = provider.read_note(row.note_path)
        assert "monthly" in note.content

    async def test_skips_when_note_already_covers_it(self, tmp_path, db_session):
        from app.models.user import User

        user = User(email=f"{uuid.uuid4()}@example.com", password_hash="x", full_name="Test", email_verified=True)
        db_session.add(user)
        db_session.commit()

        provider = self._provider(tmp_path)
        provider.create_note("01-Knowledge/HRMS Payroll.md", "# HRMS Payroll\n\nSupports weekly and monthly runs.")

        claude = _FakeCompleteProvider(responses=["SKIP"])
        worthiness = WorthinessResult(worthy=True, topic="HRMS Payroll", summary="Supports monthly runs.")

        row = await apply_sync(db_session, user, provider, claude, "chat", worthiness)

        assert row.action == KnowledgeSyncAction.skipped
        assert row.error is None

    async def test_unsafe_merge_output_is_never_written(self, tmp_path, db_session):
        """The 'if a safe merge isn't possible, do not overwrite' rule:
        anything that doesn't even look like Markdown starting with a
        heading must be rejected, not written over the real note."""
        from app.models.user import User

        user = User(email=f"{uuid.uuid4()}@example.com", password_hash="x", full_name="Test", email_verified=True)
        db_session.add(user)
        db_session.commit()

        provider = self._provider(tmp_path)
        provider.create_note("01-Knowledge/HRMS Payroll.md", "# HRMS Payroll\n\nOriginal content.")

        claude = _FakeCompleteProvider(responses=["Sure, here's a summary of your request without markdown."])
        worthiness = WorthinessResult(worthy=True, topic="HRMS Payroll", summary="Something new.")

        row = await apply_sync(db_session, user, provider, claude, "chat", worthiness)

        assert row.action == KnowledgeSyncAction.skipped
        note = provider.read_note("01-Knowledge/HRMS Payroll.md")
        assert note.content == "# HRMS Payroll\n\nOriginal content."

    async def test_topic_matches_existing_note_via_keyword_search(self, tmp_path, db_session):
        """'Retrieval Augmented Generation' should map onto an existing
        RAG note via shared vocabulary, not create a duplicate."""
        from app.models.user import User

        user = User(email=f"{uuid.uuid4()}@example.com", password_hash="x", full_name="Test", email_verified=True)
        db_session.add(user)
        db_session.commit()

        provider = self._provider(tmp_path)
        provider.create_note(
            "01-Knowledge/RAG.md",
            "# Retrieval Augmented Generation\n\nCombines retrieval with generation.",
        )

        claude = _FakeCompleteProvider(responses=["# Retrieval Augmented Generation\n\nCombines retrieval with generation. Also used for grounding chat answers."])
        worthiness = WorthinessResult(
            worthy=True, topic="Retrieval Augmented Generation", summary="Also used for grounding chat answers."
        )

        row = await apply_sync(db_session, user, provider, claude, "chat", worthiness)

        assert row.action == KnowledgeSyncAction.updated
        assert row.note_path == "01-Knowledge/RAG.md"
        # No second note should have been created for the same topic.
        assert len(provider.list_notes()) == 1


class TestFindMatchingNoteAndChooseFolder:
    def test_no_notes_returns_none(self, tmp_path):
        provider = LocalVaultProvider(tmp_path / "vault")
        assert _find_matching_note(provider, "Anything") is None

    def test_folder_chosen_from_existing_matching_folder(self, tmp_path):
        provider = LocalVaultProvider(tmp_path / "vault")
        provider.create_note("07-Research/Existing.md", "# Existing\n\nSome research note.")
        folder = _choose_folder(provider, "Research Methodology")
        assert folder == "07-Research"

    def test_folder_defaults_when_nothing_matches(self, tmp_path):
        provider = LocalVaultProvider(tmp_path / "vault")
        folder = _choose_folder(provider, "Completely Unrelated Topic Xyz")
        assert folder == "01-Knowledge"
