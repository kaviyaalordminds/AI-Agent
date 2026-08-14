from collections.abc import AsyncIterator

from app.integrations.claude.base import ClaudeMessage, ClaudeProvider, ProviderStatus
from app.integrations.claude.errors import ProviderRequestError

# Uses google-generativeai (the classic Gemini SDK). It is deprecated
# upstream in favor of google-genai, but is kept here because it has no
# dependency conflicts with this project's pinned pydantic/httpx versions
# — swap the import/client calls below for google-genai when upgrading.


class GeminiProvider(ClaudeProvider):
    """Real cloud access to Google's Gemini API — a production-mode
    alternative to Anthropic, selected via AI_PROVIDER=gemini. Construction
    is gated by the factory (GOOGLE_API_KEY must be set); any API failure
    raises ProviderRequestError rather than fabricating a reply."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            configured=True,
            provider="gemini",
            model=self._model,
            detail=f"Configured with model {self._model}.",
        )

    async def stream(
        self, messages: list[ClaudeMessage], system_prompt: str
    ) -> AsyncIterator[str]:
        import google.generativeai as genai
        from google.api_core.exceptions import GoogleAPIError

        genai.configure(api_key=self._api_key)
        model = genai.GenerativeModel(self._model, system_instruction=system_prompt)

        # Gemini's roles are "user"/"model" (not "assistant") — map full
        # multi-turn history across correctly rather than collapsing it
        # into one blob, so multi-turn AI Chat conversations keep working.
        contents = [
            {"role": "model" if m.role == "assistant" else "user", "parts": [m.content]} for m in messages
        ]

        try:
            response = await model.generate_content_async(contents, stream=True)
            async for chunk in response:
                if chunk.text:
                    yield chunk.text
        except GoogleAPIError as exc:
            raise ProviderRequestError(f"Gemini API request failed: {exc}") from exc
