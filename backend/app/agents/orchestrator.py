"""AI Agent orchestrator — seed implementation.

This is the first slice of the full pipeline described in the platform
spec:

    USER REQUEST -> UNDERSTAND -> SEARCH OBSIDIAN -> PROJECT CONTEXT ->
    MEMORY -> DETECT KNOWLEDGE -> PLAN -> CLAUDE REASONING ->
    TOOL EXECUTION -> VALIDATE -> GENERATE RESULT -> UPDATE PROJECT ->
    UPDATE OBSIDIAN -> SAVE HISTORY -> RETURN RESULT

Real today: mode-driven system prompt construction, project-context
injection, basic vault search for Knowledge/Research modes, conversation
history assembly, the actual Claude call (streamed), message persistence,
and history logging. Long-term memory, full knowledge-gap/duplicate/
outdated analysis, tool execution, and project/Obsidian auto-updates are
seams (not stubs pretending to work) — they simply aren't called yet, and
each mode's system prompt says so plainly (see prompts.py) rather than
the agent claiming capabilities it doesn't have.
"""
import logging
from collections.abc import AsyncIterator

from sqlalchemy.orm import Session

from app.agents.classifier import classify_message
from app.agents.prompts import VAULT_SEARCH_MODES, build_system_prompt
from app.database.base import utcnow
from app.integrations.claude.base import ClaudeMessage, ClaudeProvider
from app.integrations.claude.errors import ProviderRequestError
from app.integrations.obsidian.factory import get_obsidian_provider
from app.models.conversation import AgentMode, Conversation, Message, MessageRole
from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType
from app.models.project import Project

logger = logging.getLogger("agents.orchestrator")

_MAX_VAULT_RESULTS = 4
_MAX_NOTE_EXCERPT_CHARS = 500
_MAX_PROJECT_ACTIVITY_ITEMS = 8

_TITLE_MAX_LEN = 60


def _derive_title(content: str) -> str:
    content = " ".join(content.split())
    if len(content) <= _TITLE_MAX_LEN:
        return content
    return content[:_TITLE_MAX_LEN].rstrip() + "…"


def _load_message_history(db: Session, conversation_id) -> list[ClaudeMessage]:
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )
    return [ClaudeMessage(role=row.role.value, content=row.content) for row in rows if not row.error]


def _persist_user_message(db: Session, conversation: Conversation, user_content: str) -> None:
    """Always persists the user's turn, independent of whether an assistant
    reply can be produced — a user's input must never silently disappear
    just because Claude isn't configured or a request fails."""
    is_first_message = (
        db.query(Message).filter(Message.conversation_id == conversation.id).count() == 0
    )

    db.add(Message(conversation_id=conversation.id, role=MessageRole.user, content=user_content))

    if is_first_message and conversation.title in (None, "", "New conversation"):
        conversation.title = _derive_title(user_content)
        db.add(conversation)

    db.commit()


def record_unavailable_turn(
    db: Session, conversation: Conversation, user_content: str, error_detail: str
) -> None:
    """Used when a provider can't even be constructed (not configured). The
    user's message is still saved, and the failure is recorded exactly like
    a mid-stream failure would be, so the conversation and History both
    reflect what actually happened."""
    _persist_user_message(db, conversation, user_content)
    db.add(Message(conversation_id=conversation.id, role=MessageRole.assistant, content="", error=error_detail))
    _log_history(db, conversation, status=HistoryEntryStatus.failed, user_content=user_content)
    db.commit()


async def run_chat_turn(
    db: Session, conversation: Conversation, provider: ClaudeProvider, user_content: str
) -> AsyncIterator[dict]:
    """Persists the user's message, streams the assistant's reply from the
    given (already-configured) provider, and persists the result. Yields
    small event dicts ({"type": "route", ...} once, then {"type": "delta",
    "text": ...} repeatedly) so the API layer (app/api/agent/router.py)
    can forward them over SSE without owning any routing logic itself —
    this backend module is the single source of truth for provider
    selection, per the "never let the frontend bypass Obsidian-only
    technical routing" requirement.

    In AgentMode.chat specifically, every message is first classified as
    casual or technical (see app/agents/classifier.py): casual messages
    get Claude's normal free-form Chat persona; technical messages are
    routed to a strict grounded-RAG persona that may answer ONLY from
    notes retrieved from the user's Obsidian vault (see
    _search_vault_context_for_grounding), never from Claude's own
    general/training knowledge. Every other mode's existing behavior
    (Knowledge/Research's softer "ground when relevant" vault search,
    Project/Create/Developer/Automation's own personas) is unchanged.
    """
    _persist_user_message(db, conversation, user_content)

    vault_context = None
    sources: list[dict] = []
    routing_intent: str | None = None
    routing_language: str | None = None

    if conversation.mode == AgentMode.chat:
        classification = await classify_message(provider, user_content)
        routing_intent = classification.intent
        routing_language = classification.language
        if classification.intent == "technical":
            vault_context, sources = _search_vault_context_for_grounding(conversation.user_id, user_content)
    elif conversation.mode in VAULT_SEARCH_MODES:
        vault_context = _search_vault_context(conversation.user_id, user_content)

    project_activity = _build_project_activity_context(db, conversation.project)

    system_prompt = build_system_prompt(
        conversation.mode,
        conversation.project,
        vault_context,
        project_activity,
        grounded=(routing_intent == "technical"),
        language=routing_language,
    )
    history = _load_message_history(db, conversation.id)

    if routing_intent is not None:
        yield {"type": "route", "intent": routing_intent, "language": routing_language, "sources": sources}

    full_text = ""
    try:
        async for delta in provider.stream(history, system_prompt):
            full_text += delta
            yield {"type": "delta", "text": delta}
    except ProviderRequestError as exc:
        db.add(Message(conversation_id=conversation.id, role=MessageRole.assistant, content=full_text, error=str(exc)))
        _log_history(db, conversation, status=HistoryEntryStatus.failed, user_content=user_content)
        db.commit()
        raise
    else:
        db.add(Message(conversation_id=conversation.id, role=MessageRole.assistant, content=full_text))
        conversation.updated_at = utcnow()
        db.add(conversation)
        _log_history(db, conversation, status=HistoryEntryStatus.completed, user_content=user_content)
        db.commit()


def _search_vault_context(user_id, query: str) -> str:
    """Real basic-keyword vault search (see app/integrations/obsidian) used
    to ground Knowledge/Research mode replies. Never raises — a vault
    problem degrades to an honest 'no notes found' note in the prompt
    rather than failing the whole chat turn."""
    try:
        provider = get_obsidian_provider(user_id)
        results = provider.search(query)[:_MAX_VAULT_RESULTS]
    except Exception:
        logger.exception("Vault search failed for user %s", user_id)
        return "Vault search: unavailable right now (an error occurred reading the vault)."

    if not results:
        return "Vault search: no matching notes were found in the user's Obsidian vault for this message."

    blocks = ["Relevant notes from the user's Obsidian vault:"]
    for note in results:
        excerpt = note.excerpt[:_MAX_NOTE_EXCERPT_CHARS]
        blocks.append(f'- "{note.title}" ({note.path}): {excerpt}')
    return "\n".join(blocks)


def _search_vault_context_for_grounding(user_id, query: str) -> tuple[str | None, list[dict]]:
    """Same underlying vault search as _search_vault_context, but for
    AgentMode.chat's strict grounded-technical path: also returns
    structured {"title", "path"} sources for the frontend to show as
    citations, and distinguishes "the vault itself is unreachable" from
    "we searched it and found nothing" in the prompt text, since those
    are different failures Claude should describe differently to the
    user (see _GROUNDED_TECHNICAL_PROMPT in prompts.py)."""
    try:
        provider = get_obsidian_provider(user_id)
        results = provider.search(query)[:_MAX_VAULT_RESULTS]
    except Exception:
        logger.exception("Vault search failed for user %s", user_id)
        return (
            "Vault search: unavailable right now (an error occurred reading the vault). "
            "Tell the user you could not search their knowledge base right now — do not "
            "answer from your own general knowledge instead.",
            [],
        )

    if not results:
        return (
            "Vault search: no matching notes were found in the user's Obsidian vault for "
            "this message. You MUST tell the user you couldn't find this information in "
            "their knowledge base — do not answer from your own general knowledge instead.",
            [],
        )

    blocks = ["Relevant notes retrieved from the user's Obsidian vault (this is your ONLY source of truth for this reply):"]
    sources: list[dict] = []
    for note in results:
        excerpt = note.excerpt[:_MAX_NOTE_EXCERPT_CHARS]
        blocks.append(f'--- Note: "{note.title}" (path: {note.path}) ---\n{excerpt}')
        sources.append({"title": note.title, "path": note.path})
    return "\n".join(blocks), sources


def _build_project_activity_context(db: Session, project: Project | None) -> str | None:
    """Gives Project-mode (and any other project-scoped) conversations real
    awareness of what has actually happened in that project, instead of
    only its static name/description (see prompts.py). Reads HistoryEntry
    because every generation module (chat excluded — it's noise here) and
    Document/GenerationJob writer already logs there with project_id, so
    this is the one query that covers image/video/audio/document/
    knowledge-update activity without duplicating each module's own
    listing endpoint. Bounded to a handful of the most recent items so it
    never grows the prompt unboundedly."""
    if project is None:
        return None

    entries = (
        db.query(HistoryEntry)
        .filter(HistoryEntry.project_id == project.id, HistoryEntry.type != HistoryEntryType.chat)
        .order_by(HistoryEntry.created_at.desc())
        .limit(_MAX_PROJECT_ACTIVITY_ITEMS)
        .all()
    )
    if not entries:
        return None

    lines = ["Recent activity in this project (most recent first) — for your awareness only, not verbatim content:"]
    for entry in entries:
        when = (entry.completed_at or entry.created_at).strftime("%Y-%m-%d")
        lines.append(f'- [{entry.type.value}] "{entry.title}" — {entry.status.value} ({when})')
    return "\n".join(lines)


def _log_history(db: Session, conversation: Conversation, status: HistoryEntryStatus, user_content: str) -> None:
    db.add(
        HistoryEntry(
            user_id=conversation.user_id,
            project_id=conversation.project_id,
            type=HistoryEntryType.chat,
            status=status,
            title=_derive_title(user_content),
            completed_at=utcnow() if status == HistoryEntryStatus.completed else None,
        )
    )
