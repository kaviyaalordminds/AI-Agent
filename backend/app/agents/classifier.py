"""Casual-vs-technical query routing + language detection for AI Chat
(see orchestrator.run_chat_turn). One cheap Claude call classifies BOTH
intent and language semantically — Claude already reads English, Tamil,
and Tanglish (mixed Tamil-English) fluently, so this needs no separate
NLP library, embeddings, or model: the same Anthropic provider the rest
of the app already uses does the classifying. This call's own output is
never shown to the user and never itself answers the question — it's a
routing decision only. Deliberately NOT keyword-based (a plain
"contains 'what is'" check would misroute half of Tamil/Tanglish
phrasing) — the whole message is given to Claude to classify by
meaning.
"""
import json
import logging
from dataclasses import dataclass

from app.integrations.claude.base import ClaudeProvider
from app.integrations.claude.utils import complete

logger = logging.getLogger("agents.classifier")

CLASSIFIER_SYSTEM_PROMPT = """You are a precise query router for a chat assistant. Classify the user's message and respond with ONLY a single JSON object, no other text, in this exact shape:

{"intent": "casual", "language": "english"}

"intent" must be exactly one of:
- "casual": greetings, small talk, thanks, farewells, or simple pleasantries with no factual, technical, or educational content requested (e.g. "hi", "how are you", "good morning", "thank you", "bye", "nice to meet you").
- "technical": any question seeking factual, technical, educational, project-specific, or documentation-related information — including general technical/conceptual questions (e.g. "what is RAG", "explain MCP"), questions about the user's own project/knowledge base/notes/documents, and any request to search or explain documentation. Default to "technical" whenever genuinely unsure.

"language" must be exactly one of:
- "english": the message is in English.
- "tamil": the message is in Tamil script, or is a Tamil sentence written in Latin letters (transliterated Tamil).
- "tanglish": the message mixes Tamil and English words/grammar within the same sentence (code-switching), in Tamil script, Latin script, or both.

Classify based on meaning, not just which script is used or specific keywords — read the whole message before deciding."""


@dataclass
class QueryClassification:
    intent: str
    """"casual" or "technical"."""
    language: str
    """"english", "tamil", or "tanglish"."""


# Defaults to "technical"/"english" on any classification failure — the
# safer failure mode. Worst case a casual greeting gets treated as a
# knowledge-base query (an empty vault search -> a slightly stiff
# "couldn't find that in your knowledge base" reply); the alternative
# (defaulting to "casual") would let a real technical question slip
# through to Claude's ungrounded general knowledge whenever
# classification itself breaks, which is exactly the behavior this
# whole routing layer exists to prevent.
_FALLBACK = QueryClassification(intent="technical", language="english")


async def classify_message(provider: ClaudeProvider, user_content: str) -> QueryClassification:
    try:
        raw = await complete(provider, user_content, CLASSIFIER_SYSTEM_PROMPT)
    except Exception:
        logger.exception("Query classification call failed; defaulting to technical/english.")
        return _FALLBACK

    parsed = _parse_classification(raw)
    if parsed is None:
        logger.warning("Query classifier returned unparseable output: %r", raw[:200])
        return _FALLBACK
    return parsed


def _parse_classification(raw: str) -> QueryClassification | None:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    intent = data.get("intent")
    language = data.get("language")
    if intent not in ("casual", "technical") or language not in ("english", "tamil", "tanglish"):
        return None
    return QueryClassification(intent=intent, language=language)
