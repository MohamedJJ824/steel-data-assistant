"""Ollama backend.

Local inference, so no data leaves the machine. Two model-specific quirks are
handled here rather than by every caller:

* `think: false` does not suppress reasoning on qwen3 — it leaks into
  `message.content` as prose while `message.thinking` stays empty. Prepending
  the `/no_think` directive to the last user message does work.
* Reasoning that slips through anyway is stripped from the returned content.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from steel_assistant.config import get_settings
from steel_assistant.llm.base import LLMResponse, ToolCall, strip_reasoning

NO_THINK = "/no_think"


class OllamaClient:
    """Talks to a local Ollama server over its native chat API."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        default_model: str | None = None,
        timeout_s: int | None = None,
        suppress_reasoning: bool | None = None,
    ) -> None:
        """Configure the client. Defaults come from config/default.yaml."""
        settings = get_settings().llm
        self.base_url = (base_url or settings.base_url).rstrip("/")
        self.default_model = default_model or settings.agent_model
        self.timeout_s = timeout_s or settings.timeout_s
        self.temperature = settings.temperature
        self.num_ctx = settings.num_ctx
        self.suppress_reasoning = (
            settings.suppress_reasoning if suppress_reasoning is None else suppress_reasoning
        )
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout_s)

    def is_available(self) -> bool:
        """True when the server answers its version endpoint."""
        try:
            return self._client.get("/api/version", timeout=5).status_code == 200
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[str]:
        """Names of the models the server has pulled."""
        response = self._client.get("/api/tags")
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]

    def _prepare(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Append the reasoning-suppression directive to the last user turn."""
        if not self.suppress_reasoning:
            return messages
        prepared = [dict(m) for m in messages]
        for message in reversed(prepared):
            if message.get("role") == "user":
                content = str(message.get("content", ""))
                if NO_THINK not in content:
                    message["content"] = f"{NO_THINK} {content}"
                break
        return prepared

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to /api/chat, retrying twice on transport failures."""
        response = self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        return response.json()

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Send a conversation and return one completion.

        ``response_format`` is a JSON schema passed straight through to
        Ollama's ``format`` field, which constrains decoding to valid JSON.
        """
        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": self._prepare(messages),
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "temperature": self.temperature if temperature is None else temperature,
                "num_ctx": self.num_ctx,
            },
        }
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["format"] = response_format

        started = time.perf_counter()
        data = self._post(payload)
        latency_ms = int((time.perf_counter() - started) * 1000)

        message = data.get("message", {}) or {}
        content = strip_reasoning(str(message.get("content") or ""))

        tool_calls = [
            ToolCall(
                name=call["function"]["name"],
                arguments=call["function"].get("arguments") or {},
                call_id=call.get("id"),
            )
            for call in (message.get("tool_calls") or [])
        ]

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            model=data.get("model", ""),
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
            latency_ms=latency_ms,
            finish_reason=data.get("done_reason"),
        )

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()
