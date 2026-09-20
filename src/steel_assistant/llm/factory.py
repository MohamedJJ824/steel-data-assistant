"""Backend selection. Everything downstream depends on the protocol, not a class."""

from __future__ import annotations

from steel_assistant.config import Settings, get_settings
from steel_assistant.llm.base import LLMClient
from steel_assistant.llm.ollama import OllamaClient
from steel_assistant.llm.openai_compatible import OpenAICompatibleClient


def build_llm_client(settings: Settings | None = None, *, model: str | None = None) -> LLMClient:
    """Return the client for the configured backend."""
    settings = settings or get_settings()
    if settings.llm.backend == "ollama":
        return OllamaClient(default_model=model)
    return OpenAICompatibleClient(default_model=model)
