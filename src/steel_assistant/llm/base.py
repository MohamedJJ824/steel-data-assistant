"""The LLM client protocol shared by every backend."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# qwen3 and its relatives emit their reasoning inside these tags. When the
# suppression directive is ignored, strip them rather than let a model's
# internal monologue reach the user or a JSON parser.
_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


@dataclass(slots=True)
class ToolCall:
    """A tool invocation requested by the model."""

    name: str
    arguments: dict[str, Any]
    call_id: str | None = None


@dataclass(slots=True)
class LLMResponse:
    """One completion, plus whatever accounting the backend gave us."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int = 0
    finish_reason: str | None = None

    @property
    def total_tokens(self) -> int | None:
        """Prompt plus completion tokens, when the backend reported both."""
        if self.prompt_tokens is None or self.completion_tokens is None:
            return None
        return self.prompt_tokens + self.completion_tokens


def strip_reasoning(text: str) -> str:
    """Remove any `<think>...</think>` block from a completion.

    Defensive: `/no_think` handles this on qwen3, but that directive is a
    model-specific convention a backend swap would silently drop.
    """
    return _THINK_BLOCK.sub("", text).strip()


@runtime_checkable
class LLMClient(Protocol):
    """What the agent, the tools and the evaluation judge all depend on."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Send a conversation and return one completion."""
        ...

    def is_available(self) -> bool:
        """True when the backend answers. Used by /health."""
        ...
