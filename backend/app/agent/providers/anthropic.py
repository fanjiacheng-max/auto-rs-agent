import anthropic
from app.config import ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL, CLAUDE_MODEL
from app.agent.providers.base import ContentBlock, LLMProvider, LLMResponse


def _build_client() -> anthropic.Anthropic:
    kwargs: dict = {}

    if ANTHROPIC_BASE_URL:
        kwargs["base_url"] = ANTHROPIC_BASE_URL

    if ANTHROPIC_AUTH_TOKEN:
        kwargs["auth_token"] = ANTHROPIC_AUTH_TOKEN
    elif ANTHROPIC_API_KEY:
        kwargs["api_key"] = ANTHROPIC_API_KEY
    # If neither is set, let the SDK raise its own auth error

    return anthropic.Anthropic(**kwargs)


class AnthropicProvider(LLMProvider):
    def __init__(self) -> None:
        self._client = _build_client()

    async def chat(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        import asyncio

        def _call():
            return self._client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=8192,
                system=system,
                tools=tools,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            )

        # Run sync SDK call in a thread to avoid blocking the event loop
        response = await asyncio.get_event_loop().run_in_executor(None, _call)

        blocks: list[ContentBlock] = []
        for block in response.content:
            if block.type == "text":
                blocks.append(ContentBlock(type="text", text=block.text))
            elif block.type == "tool_use":
                blocks.append(ContentBlock(
                    type="tool_use",
                    tool_name=block.name,
                    tool_use_id=block.id,
                    tool_input=block.input,
                ))

        return LLMResponse(content=blocks, stop_reason=response.stop_reason)

    @staticmethod
    def serialize_message_content(content: list[ContentBlock]) -> list[dict]:
        """Convert ContentBlocks back to Anthropic API format for message history."""
        result = []
        for b in content:
            if b.type == "text":
                result.append({"type": "text", "text": b.text or ""})
            elif b.type == "tool_use":
                result.append({
                    "type": "tool_use",
                    "id": b.tool_use_id,
                    "name": b.tool_name,
                    "input": b.tool_input or {},
                })
        return result
