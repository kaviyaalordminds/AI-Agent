import json
from collections.abc import AsyncIterator

import httpx

from app.integrations.claude.base import ClaudeMessage, ClaudeProvider, ProviderStatus
from app.integrations.claude.errors import ProviderRequestError


class OllamaProvider(ClaudeProvider):
    """Real local-model access via a running Ollama server
    (https://ollama.com) — the default AI provider for local development,
    since it needs no API key or outbound internet access. Construction is
    gated by the factory (model must be configured); any connection
    failure or non-2xx response at request time raises
    ProviderRequestError rather than fabricating a reply — Ollama being
    unreachable is a real, reportable failure, not silently papered over.
    """

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            configured=True,
            provider="ollama",
            model=self._model,
            detail=f"Configured to use Ollama at {self._base_url} with model '{self._model}'.",
        )

    async def stream(
        self, messages: list[ClaudeMessage], system_prompt: str
    ) -> AsyncIterator[str]:
        ollama_messages = [{"role": "system", "content": system_prompt}]
        ollama_messages += [{"role": m.role, "content": m.content} for m in messages]

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/api/chat",
                    json={"model": self._model, "messages": ollama_messages, "stream": True},
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        raise ProviderRequestError(
                            f"Ollama request failed ({response.status_code}): {body.decode(errors='replace')[:300]}"
                        )
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            payload = json.loads(line)
                        except ValueError:
                            continue
                        if payload.get("error"):
                            raise ProviderRequestError(f"Ollama error: {payload['error']}")
                        chunk = payload.get("message", {}).get("content", "")
                        if chunk:
                            yield chunk
                        if payload.get("done"):
                            break
        except httpx.RequestError as exc:
            raise ProviderRequestError(
                f"Could not reach Ollama at {self._base_url}: {exc}. "
                "Is `ollama serve` running on this machine?"
            ) from exc
