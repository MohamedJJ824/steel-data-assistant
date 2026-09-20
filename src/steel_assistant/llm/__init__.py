"""LLM client protocol and its backends (Ollama, OpenAI-compatible)."""

from steel_assistant.llm.base import LLMClient, LLMResponse, ToolCall, strip_reasoning
from steel_assistant.llm.factory import build_llm_client

__all__ = [
    "LLMClient",
    "LLMResponse",
    "ToolCall",
    "build_llm_client",
    "strip_reasoning",
]
