from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ContentBlock:
    type: str  # "text" | "tool_use"
    text: str | None = None        # when type == "text"
    tool_name: str | None = None   # when type == "tool_use"
    tool_use_id: str | None = None
    tool_input: dict | None = None


@dataclass
class LLMResponse:
    content: list[ContentBlock]
    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens"


class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        ...
