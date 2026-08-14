"""AI Agent orchestrator — seed implementation.

This is the first slice of the full pipeline described in the platform
spec:

    USER REQUEST -> UNDERSTAND -> SEARCH OBSIDIAN -> PROJECT CONTEXT ->
    MEMORY -> DETECT KNOWLEDGE -> PLAN -> CLAUDE REASONING ->
    TOOL EXECUTION -> VALIDATE -> GENERATE RESULT -> UPDATE PROJECT ->
    UPDATE OBSIDIAN -> SAVE HISTORY -> RETURN RESULT

Real today: mode-driven system prompt construction, project-context
injection, conversation history assembly, the actual Claude call
(streamed), message persistence, and history logging. Obsidian search,
long-term memory, knowledge-gap detection, tool execution, and
project/Obsidian auto-updates are seams (not stubs pretending to work) —
they simply aren't called yet, and each mode's system prompt says so
plainly (see prompts.py) rather than the agent claiming capabilities it
doesn't have.
"""
from collections.abc import AsyncIterator

from sqlalchemy.orm import Session

from app.agents.prompts import build_system_prompt
from app.database.base import utcnow
from app.integrations.claude.base import ClaudeMessage, ClaudeProvider
from app.integrations.claude.errors import ProviderRequestError
from app.models.conversation import Conversation, Message, MessageRole
from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType

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
) -> AsyncIterator[str]:
    """Persists the user's message, streams the assistant's reply from the
    given (already-configured) provider, and persists the result. Yields
    text deltas as they arrive so the API layer can forward them over SSE.
    """
    _persist_user_message(db, conversation, user_content)

    system_prompt = build_system_prompt(conversation.mode, conversation.project)
    history = _load_message_history(db, conversation.id)

    full_text = ""
    try:
        async for delta in provider.stream(history, system_prompt):
            full_text += delta
            yield delta
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
