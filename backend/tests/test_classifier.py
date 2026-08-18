"""Unit tests for app/agents/classifier.py's parsing/fallback behavior,
independent of the full chat-turn pipeline (see test_agent.py::
TestChatRouting for the end-to-end routing tests)."""
import pytest

from app.agents.classifier import QueryClassification, _FALLBACK, classify_message
from app.integrations.claude.base import ClaudeMessage, ClaudeProvider, ProviderStatus
from app.integrations.claude.errors import ProviderRequestError


class _ScriptedProvider(ClaudeProvider):
    def __init__(self, response_text: str | None = None, raise_error: Exception | None = None):
        self._response_text = response_text
        self._raise_error = raise_error

    def status(self) -> ProviderStatus:
        return ProviderStatus(configured=True, provider="fake", model="fake-model", detail="ok")

    async def stream(self, messages: list[ClaudeMessage], system_prompt: str):
        if self._raise_error is not None:
            raise self._raise_error
        yield self._response_text


class TestClassifyMessage:
    @pytest.mark.asyncio
    async def test_parses_clean_json(self):
        provider = _ScriptedProvider('{"intent": "casual", "language": "english"}')
        result = await classify_message(provider, "hi")
        assert result == QueryClassification(intent="casual", language="english")

    @pytest.mark.asyncio
    async def test_parses_json_wrapped_in_markdown_fence(self):
        provider = _ScriptedProvider('```json\n{"intent": "technical", "language": "tamil"}\n```')
        result = await classify_message(provider, "RAG na enna?")
        assert result == QueryClassification(intent="technical", language="tamil")

    @pytest.mark.asyncio
    async def test_parses_json_with_surrounding_commentary(self):
        provider = _ScriptedProvider('Sure, here you go: {"intent": "technical", "language": "tanglish"} Hope that helps!')
        result = await classify_message(provider, "MCP server epdi work aaguthu?")
        assert result == QueryClassification(intent="technical", language="tanglish")

    @pytest.mark.asyncio
    async def test_unparseable_output_falls_back_to_technical_english(self):
        provider = _ScriptedProvider("I'm not sure how to classify that.")
        result = await classify_message(provider, "anything")
        assert result == _FALLBACK
        assert result.intent == "technical"

    @pytest.mark.asyncio
    async def test_invalid_enum_values_fall_back(self):
        provider = _ScriptedProvider('{"intent": "maybe", "language": "english"}')
        result = await classify_message(provider, "anything")
        assert result == _FALLBACK

    @pytest.mark.asyncio
    async def test_provider_failure_falls_back_instead_of_raising(self):
        """A classification-call failure must never crash the whole chat
        turn — the real answer call right after will surface the actual
        provider error through the existing, already-tested error path."""
        provider = _ScriptedProvider(raise_error=ProviderRequestError("quota exceeded"))
        result = await classify_message(provider, "anything")
        assert result == _FALLBACK
