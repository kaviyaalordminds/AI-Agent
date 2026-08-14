from collections.abc import AsyncIterator

import anthropic

from app.integrations.claude.base import ClaudeMessage, ClaudeProvider, ProviderStatus
from app.integrations.claude.errors import ProviderRequestError


class AnthropicApiProvider(ClaudeProvider):
    """Real Claude access via the standard Anthropic API (api.anthropic.com),
    authenticated with ANTHROPIC_API_KEY. This is the production-honest
    implementation: it does not fall back to a mock response if the key is
    missing or invalid — construction is gated by the factory
    (see factory.py), and any in-flight API failure raises
    ProviderRequestError rather than fabricating output.
    """

    def __init__(self, api_key: str, model: str, max_output_tokens: int) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_output_tokens = max_output_tokens

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            configured=True,
            provider="anthropic",
            model=self._model,
            detail=f"Configured with model {self._model}.",
        )

    async def stream(
        self, messages: list[ClaudeMessage], system_prompt: str
    ) -> AsyncIterator[str]:
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=self._max_output_tokens,
                system=system_prompt,
                messages=api_messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.APIError as exc:
            raise ProviderRequestError(f"Claude API request failed: {exc}") from exc
