"""Automatic Knowledge Maintenance Agent: the piece that keeps the user's
Obsidian vault current WITHOUT the user ever manually pressing "update
Obsidian". Runs after a chat turn (see app/agents/orchestrator.py's call
to sync_knowledge) against the user's own message text.

Distinct role from AI Chat's Claude usage (app/agents/classifier.py,
app/agents/prompts.py's grounded-technical persona): this module's Claude
calls never answer the user directly — they only decide (a) is this
message durable, worth-persisting knowledge at all, (b) does an existing
note already cover it or is this new, and (c) what minimal Markdown change
keeps the vault accurate. Casual chat and knowledge maintenance are two
independent Claude call sites that happen to share the same provider —
this module is never the technical-answer provider for normal AI Chat.

Safety contract, matching the ObsidianProvider write path already used
everywhere else in this app (app/api/obsidian/router.py): every write goes
through provider.create_note()/update_note()/append_note(), which in turn
always run target paths through validate_obsidian_path() (see
app/integrations/obsidian/local_vault_provider.py) — this module never
touches the filesystem directly and never invents its own path validation,
so a path derived here can never escape the vault any more than a manual
Obsidian API call could. Every outcome (created/updated/skipped, or a
caught failure) is persisted as a KnowledgeSync row so the sync history is
never silently lost, and nothing here ever raises out to break the chat
turn that triggered it — any failure degrades to a "skipped" record
carrying the real error message.
"""
import json
import logging
import re

from sqlalchemy.orm import Session

from app.integrations.claude.base import ClaudeProvider
from app.integrations.claude.utils import complete
from app.integrations.obsidian.base import ObsidianProvider
from app.integrations.obsidian.errors import InvalidNotePathError, NoteAlreadyExistsError, NoteNotFoundError
from app.models.knowledge_sync import KnowledgeSync, KnowledgeSyncAction
from app.models.user import User

logger = logging.getLogger("knowledge.sync_agent")

_MIN_MESSAGE_CHARS = 20
_MAX_EXISTING_CONTENT_CHARS = 4000
_DEFAULT_FOLDER = "01-Knowledge"

# Cheap heuristic pre-filter before spending a Claude call: messages this
# short or this exact-shaped essentially can never be a project
# requirement, architecture decision, or spec. This only ever SKIPS the
# worthiness call early — it never decides "worthy" on its own — so it
# can't wrongly persist anything; the worthiness prompt below remains the
# sole "is this durable knowledge" arbiter for everything that passes it.
_TRIVIAL_PATTERN = re.compile(
    r"^(hi|hello|hey|hii+|good\s*(morning|afternoon|evening|night)|how\s+are\s+you\??|"
    r"thanks?( you)?|thank\s*you|bye|goodbye|see\s+you|nice\s+to\s+meet\s+you|"
    r"ok(ay)?|yes|no|sure|cool|great|what'?s\s+the\s+weather.*)\s*[.!?]*$",
    re.IGNORECASE,
)

_WORTHINESS_SYSTEM_PROMPT = """You decide whether a single chat message from a user contains durable knowledge worth permanently recording in their personal knowledge base (an Obsidian vault), or whether it's just conversational filler.

Respond with ONLY a JSON object, no other text, in exactly this shape:
{"worthy": true, "topic": "short topic title", "summary": "1-4 sentence durable fact/decision extracted from the message, written in third person, self-contained (understandable without the original chat)"}

Mark worthy=true ONLY for messages that state or imply something durable and reusable later, such as:
- a new project requirement or specification
- a technical architecture or design decision
- a new feature specification
- API/configuration details worth remembering
- an important business requirement or decision
- an explanation or correction of a technical concept the user wants remembered

Mark worthy=false for EVERYTHING else, including:
- greetings, small talk, thanks, farewells ("hi", "how are you", "thank you")
- questions the user is ASKING (a question seeking information is not itself new knowledge to store — only store durable statements/decisions, not queries)
- vague or incomplete statements with no concrete, reusable content
- anything trivial, temporary, or not worth remembering days from now

When worthy=false, omit "topic" and "summary" (or set them to null). Never fabricate detail beyond what the message actually says."""

_MERGE_SYSTEM_PROMPT = """You maintain one note in a user's personal knowledge base. You will be given the note's current Markdown content and a new piece of information to incorporate.

Decide: does the note ALREADY substantially cover this new information (even if worded differently)? If so, respond with EXACTLY the single word:
SKIP

Otherwise, respond with the COMPLETE updated Markdown for the note (nothing else — no commentary, no code fences), following these rules:
- Preserve ALL existing sections, headings, and content that are still accurate — never delete or rewrite unrelated material.
- Integrate the new information into the most appropriate existing section, or add a new section if none fits, matching the note's existing heading style/structure.
- Never duplicate a paragraph or bullet that already states the same fact.
- Keep the note's existing title (the first '# ' heading) unchanged.
- Output the full note content, ready to save as-is."""

_NEW_NOTE_SYSTEM_PROMPT = """Write a new Markdown note for a user's personal knowledge base, capturing the given durable information.

Respond with ONLY the Markdown content, nothing else:
- Start with a single '# Title' heading matching the topic.
- Organize the content clearly (short sections/bullets as appropriate).
- Include only what is actually known from the given information — do not invent extra detail.
- Keep it concise; this is a reference note, not an essay."""


class WorthinessResult:
    def __init__(self, worthy: bool, topic: str | None = None, summary: str | None = None):
        self.worthy = worthy
        self.topic = topic
        self.summary = summary


def _parse_json_object(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None


async def assess_knowledge_worthiness(provider: ClaudeProvider, text: str) -> WorthinessResult:
    """Never raises — any failure degrades to worthy=False (the safe
    default: skipping a sync is recoverable, an unwanted/garbled vault
    write is not)."""
    stripped = text.strip()
    if len(stripped) < _MIN_MESSAGE_CHARS or _TRIVIAL_PATTERN.match(stripped):
        return WorthinessResult(worthy=False)

    try:
        raw = await complete(provider, stripped, _WORTHINESS_SYSTEM_PROMPT)
    except Exception:
        logger.exception("Knowledge worthiness assessment call failed; skipping sync.")
        return WorthinessResult(worthy=False)

    data = _parse_json_object(raw)
    if data is None or not isinstance(data.get("worthy"), bool) or not data["worthy"]:
        return WorthinessResult(worthy=False)
    topic = (data.get("topic") or "").strip()
    summary = (data.get("summary") or "").strip()
    if not topic or not summary:
        return WorthinessResult(worthy=False)
    return WorthinessResult(worthy=True, topic=topic, summary=summary)


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _find_matching_note(provider: ObsidianProvider, topic: str):
    """Duplicate prevention: exact/normalized title match first (highest
    confidence), then falls back to the provider's own keyword search
    (already used throughout the app for vault grounding) so a topic like
    'Retrieval Augmented Generation' can still land on an existing
    'RAG.md' note via shared vocabulary even without an exact title
    match."""
    normalized_topic = _normalize_title(topic)
    candidates = provider.search(topic)
    for note in candidates:
        if _normalize_title(note.title) == normalized_topic:
            return note
    return candidates[0] if candidates else None


def _safe_folder_slug(topic: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9 _-]", "", topic).strip()
    slug = re.sub(r"\s+", " ", slug)
    return slug[:80] or "Untitled"


def _choose_folder(provider: ObsidianProvider, topic: str) -> str:
    """Looks for an existing folder whose name shares a word with the
    topic (matching the vault's own organization instead of always
    dumping new notes in one place); falls back to the default
    01-Knowledge folder every vault is provisioned with."""
    try:
        existing = provider.list_notes()
    except Exception:
        return _DEFAULT_FOLDER

    topic_words = set(_normalize_title(topic).split())
    folders = {note.folder for note in existing if note.folder}
    for folder in folders:
        folder_words = set(_normalize_title(folder.rsplit("/", 1)[-1]).split())
        if topic_words & folder_words:
            return folder
    return _DEFAULT_FOLDER


async def sync_knowledge(
    db: Session,
    user: User,
    obsidian_provider: ObsidianProvider,
    claude_provider: ClaudeProvider,
    source: str,
    text: str,
) -> KnowledgeSync | None:
    """The Knowledge Maintenance Agent's entry point. Returns None (no
    KnowledgeSync row at all) when the message wasn't even assessed as
    knowledge-worthy — the "do not sync on every casual chat message"
    rule — so the sync history only ever records genuine sync attempts,
    not every single chat turn. Every attempt beyond that point (worthy
    but a duplicate, created, updated, or failed) is recorded.

    Callers that need to react to the worthiness decision BEFORE the
    (potentially slower) search/merge/create work runs — e.g. the chat
    orchestrator, which only shows a "Updating Obsidian…" status once a
    sync is actually going to happen — should call
    assess_knowledge_worthiness() themselves first and use apply_sync()
    directly instead of this all-in-one wrapper, to avoid asking Claude to
    assess the same message twice."""
    worthiness = await assess_knowledge_worthiness(claude_provider, text)
    if not worthiness.worthy:
        return None
    return await apply_sync(db, user, obsidian_provider, claude_provider, source, worthiness)


async def apply_sync(
    db: Session,
    user: User,
    obsidian_provider: ObsidianProvider,
    claude_provider: ClaudeProvider,
    source: str,
    worthiness: WorthinessResult,
) -> KnowledgeSync:
    """Given an already-worthy assessment, does the actual vault
    search/merge/create work and always returns a KnowledgeSync row (never
    None — by this point a sync attempt is definitely happening)."""

    def _record(
        action: KnowledgeSyncAction, description: str, note_path: str | None = None, error: str | None = None
    ) -> KnowledgeSync:
        row = KnowledgeSync(
            user_id=user.id,
            source=source,
            topic=worthiness.topic,
            action=action,
            note_path=note_path,
            description=description,
            error=error,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    try:
        try:
            match = _find_matching_note(obsidian_provider, worthiness.topic)
        except Exception as exc:
            return _record(KnowledgeSyncAction.skipped, "Could not search the vault for a matching topic.", error=str(exc))

        if match is not None:
            try:
                detail = obsidian_provider.read_note(match.path)
            except (NoteNotFoundError, InvalidNotePathError) as exc:
                return _record(
                    KnowledgeSyncAction.skipped, f"Matched note '{match.path}' could not be read.", note_path=match.path, error=str(exc)
                )

            merge_message = (
                f"New information:\n{worthiness.summary}\n\n"
                f"Current note content (path: {match.path}):\n{detail.content[:_MAX_EXISTING_CONTENT_CHARS]}"
            )
            try:
                merged = (await complete(claude_provider, merge_message, _MERGE_SYSTEM_PROMPT)).strip()
            except Exception as exc:
                logger.exception("Knowledge merge call failed for topic %r.", worthiness.topic)
                return _record(
                    KnowledgeSyncAction.skipped, "Merge generation failed; note left unchanged.", note_path=match.path, error=str(exc)
                )

            if merged == "SKIP" or not merged:
                return _record(
                    KnowledgeSyncAction.skipped, "Existing note already covers this information.", note_path=match.path
                )
            if not merged.startswith("#"):
                # Never trust the model's output blindly as a full-file
                # replacement if it doesn't even look like the requested
                # Markdown note — log and skip rather than risk a
                # destructive overwrite (the "if a safe merge isn't
                # possible, do not overwrite" rule).
                return _record(
                    KnowledgeSyncAction.skipped,
                    "Generated update did not look like a valid Markdown note; left unchanged to avoid an unsafe overwrite.",
                    note_path=match.path,
                )

            try:
                obsidian_provider.update_note(match.path, merged)
            except (InvalidNotePathError, NoteNotFoundError) as exc:
                return _record(KnowledgeSyncAction.skipped, "Vault rejected the update.", note_path=match.path, error=str(exc))

            return _record(
                KnowledgeSyncAction.updated,
                f"Updated existing note with new information about '{worthiness.topic}'.",
                note_path=match.path,
            )

        # No matching note — create a new one.
        folder = _choose_folder(obsidian_provider, worthiness.topic)
        try:
            content = (await complete(claude_provider, worthiness.summary, _NEW_NOTE_SYSTEM_PROMPT)).strip()
        except Exception as exc:
            logger.exception("New-note generation call failed for topic %r.", worthiness.topic)
            return _record(KnowledgeSyncAction.skipped, "Note generation failed.", error=str(exc))

        if not content.startswith("#"):
            content = f"# {worthiness.topic}\n\n{content}"

        path = f"{folder}/{_safe_folder_slug(worthiness.topic)}.md"
        try:
            created = obsidian_provider.create_note(path, content)
        except NoteAlreadyExistsError:
            # A race with a concurrent sync/manual edit — fall back to
            # append rather than erroring the whole turn.
            try:
                created = obsidian_provider.append_note(path, f"\n\n{content}")
            except (InvalidNotePathError, NoteNotFoundError) as exc:
                return _record(KnowledgeSyncAction.skipped, "Vault rejected the new note.", error=str(exc))
        except InvalidNotePathError as exc:
            return _record(KnowledgeSyncAction.skipped, "Vault rejected the new note path.", error=str(exc))

        return _record(
            KnowledgeSyncAction.created, f"Created a new note for '{worthiness.topic}'.", note_path=created.path
        )
    except Exception as exc:  # noqa: BLE001 - last resort: never let this break the chat turn that triggered it
        logger.exception("Knowledge sync failed unexpectedly for topic %r.", worthiness.topic)
        return _record(KnowledgeSyncAction.skipped, "Sync failed due to an unexpected error.", error=str(exc))
