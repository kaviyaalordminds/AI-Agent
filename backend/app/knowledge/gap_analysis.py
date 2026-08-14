"""Claude-backed knowledge gap analysis (spec section 22).

Unlike duplicate/outdated/broken-link detection (vault_analysis.py, pure
deterministic string/date comparison), answering "what am I missing for a
manufacturing HRMS" requires knowing what a manufacturing HRMS domain
normally includes — that's world knowledge only an LLM has. So this module
follows the exact same honesty contract as AI Chat (app/agents/): a
query's text is always persisted regardless of outcome, and if Claude
isn't configured the analysis is recorded as failed with the real error
message rather than silently discarded or faked.
"""
import re

from sqlalchemy.orm import Session

from app.database.base import utcnow
from app.integrations.claude.base import ClaudeProvider
from app.integrations.claude.errors import ProviderRequestError
from app.integrations.claude.utils import complete
from app.integrations.obsidian.base import ObsidianProvider
from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType
from app.models.knowledge_analysis import KnowledgeAnalysis, KnowledgeAnalysisStatus
from app.models.project import Project
from app.models.user import User

_MAX_CONTEXT_NOTES = 6
_MAX_NOTE_CHARS = 600

_SYSTEM_PROMPT = """You are the Knowledge Intelligence engine of the AI Agent Platform.
The user will describe something they want to build or work on, along with
excerpts of any related notes already in their Obsidian vault (there may be
none). Compare the request against what's already documented and respond
in EXACTLY this format, with each section header on its own line in caps,
followed by one bullet per line starting with "- " (write "- None." if a
section is empty):

EXISTING:
- (knowledge the user's notes already cover, relevant to the request)

MISSING:
- (specific, concrete things a project/topic like this would typically need
  that are NOT covered by the existing notes — be specific to the domain,
  not generic)

RECOMMENDED:
- (concrete next actions: notes to create, topics to research)

DUPLICATES:
- (pairs of provided notes that appear to cover overlapping ground, if any)

OUTDATED:
- (anything in the provided notes that looks stale or superseded, if you
  can tell from the text — do not guess ages you weren't told)

Be concrete and specific to the stated request's domain. Do not claim the
user's vault contains something it wasn't shown to contain."""

_SECTION_ORDER = ["EXISTING", "MISSING", "RECOMMENDED", "DUPLICATES", "OUTDATED"]


def _parse_response(raw: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {name: [] for name in _SECTION_ORDER}
    current = None
    for line in raw.splitlines():
        stripped = line.strip()
        header_match = re.match(r"^([A-Z]+):\s*$", stripped)
        if header_match and header_match.group(1) in sections:
            current = header_match.group(1)
            continue
        if current and stripped.startswith("- "):
            item = stripped[2:].strip()
            if item and item.lower() not in ("none.", "none"):
                sections[current].append(item)
    return sections


def _build_context(notes) -> str:
    if not notes:
        return "No related notes were found in the vault for this request."
    blocks = []
    for note in notes[:_MAX_CONTEXT_NOTES]:
        blocks.append(f'### "{note.title}" ({note.path})\n{note.excerpt[:_MAX_NOTE_CHARS]}')
    return "\n\n".join(blocks)


def _record_failed_analysis(
    db: Session, user: User, project: Project | None, query: str, error_detail: str
) -> KnowledgeAnalysis:
    analysis = KnowledgeAnalysis(
        user_id=user.id,
        project_id=project.id if project else None,
        query=query,
        status=KnowledgeAnalysisStatus.failed,
        error=error_detail,
    )
    db.add(analysis)
    _log_history(db, user, project, query, HistoryEntryStatus.failed)
    db.commit()
    db.refresh(analysis)
    return analysis


def record_unavailable_analysis(
    db: Session, user: User, project: Project | None, query: str, error_detail: str
) -> KnowledgeAnalysis:
    """Provider couldn't even be constructed — persist the query anyway so
    it isn't lost, exactly like record_unavailable_turn does for chat."""
    return _record_failed_analysis(db, user, project, query, error_detail)


async def run_gap_analysis(
    db: Session,
    user: User,
    project: Project | None,
    obsidian_provider: ObsidianProvider,
    claude_provider: ClaudeProvider,
    query: str,
) -> KnowledgeAnalysis:
    related_notes = obsidian_provider.search(query)
    context = _build_context(related_notes)
    message = f"Request: {query}\n\nRelated notes already in the vault:\n\n{context}"

    try:
        raw = await complete(claude_provider, message, _SYSTEM_PROMPT)
    except ProviderRequestError as exc:
        return _record_failed_analysis(db, user, project, query, str(exc))

    sections = _parse_response(raw)
    analysis = KnowledgeAnalysis(
        user_id=user.id,
        project_id=project.id if project else None,
        query=query,
        status=KnowledgeAnalysisStatus.completed,
        existing_summary="\n".join(sections["EXISTING"]) or None,
        missing_items=sections["MISSING"],
        recommended_additions=sections["RECOMMENDED"],
        duplicate_notes=sections["DUPLICATES"],
        outdated_notes=sections["OUTDATED"],
        raw_response=raw,
    )
    db.add(analysis)
    _log_history(db, user, project, query, HistoryEntryStatus.completed)
    db.commit()
    db.refresh(analysis)
    return analysis


def _log_history(
    db: Session, user: User, project: Project | None, query: str, status: HistoryEntryStatus
) -> None:
    title = query if len(query) <= 60 else query[:60].rstrip() + "…"
    db.add(
        HistoryEntry(
            user_id=user.id,
            project_id=project.id if project else None,
            type=HistoryEntryType.knowledge_update,
            status=status,
            title=f"Knowledge gap analysis: {title}",
            completed_at=utcnow() if status == HistoryEntryStatus.completed else None,
        )
    )
