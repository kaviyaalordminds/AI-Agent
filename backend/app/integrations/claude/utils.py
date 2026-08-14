from app.integrations.claude.base import ClaudeMessage, ClaudeProvider


async def complete(provider: ClaudeProvider, message: str, system_prompt: str) -> str:
    """Run a single-turn prompt against a streaming ClaudeProvider and
    return the fully-accumulated text. For callers (gap analysis, document
    generation) that need one finished response rather than incremental
    deltas — the underlying provider is still real streaming, this just
    collects it."""
    full_text = ""
    async for delta in provider.stream([ClaudeMessage(role="user", content=message)], system_prompt):
        full_text += delta
    return full_text
