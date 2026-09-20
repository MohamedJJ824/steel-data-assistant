"""OpenAI-compatible backend.

Used when a hosted endpoint is configured instead of local inference: faster
iteration, and a stronger judge model for evaluation. Selected by
``llm.backend``, so nothing else in the codebase changes.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from steel_assistant.config import get_settings
from steel_assistant.llm.base import LLMResponse, ToolCall, strip_reasoning


class OpenAICompatibleClient:
    """Talks to any server exposing /v1/chat/completions."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout_s: int | None = None,
    ) -> None:
        """Configure the client. Defaults come from config/default.yaml."""
        settings = get_settings().llm
        self.base_url = (base_url or settings.base_url).rstrip("/")
        self.default_model = default_model or settings.agent_model
        self.timeout_s = timeout_s or settings.timeout_s
        self.temperature = settings.temperature
        key = api_key if api_key is not None else settings.api_key.get_secret_value()
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout_s, headers=headers)

    def is_available(self) -> bool:
        """True when the server lists its models."""
        try:
            return self._client.get("/v1/models", timeout=5).status_code == 200
        except httpx.HTTPError:
            return False

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to /v1/chat/completions, retrying twice on transport failures."""
        response = self._client.post("/v1/chat/completions", json=payload)
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

        ``response_format`` takes the same JSON schema the Ollama backend
        accepts, and is wrapped into the OpenAI ``json_schema`` envelope here so
        that callers stay backend-agnostic.
        """
        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
        }
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": response_format,
                    "strict": True,
                },
            }

        started = time.perf_counter()
        data = self._post(payload)
        latency_ms = int((time.perf_counter() - started) * 1000)

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {}) or {}
        usage = data.get("usage", {}) or {}

        tool_calls = []
        for call in message.get("tool_calls") or []:
            function = call.get("function", {})
            raw_args = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(
                ToolCall(
                    name=function.get("name", ""),
                    arguments=arguments,
                    call_id=call.get("id"),
                )
            )

        return LLMResponse(
            content=strip_reasoning(str(message.get("content") or "")),
            tool_calls=tool_calls,
            model=data.get("model", ""),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=latency_ms,
            finish_reason=choice.get("finish_reason"),
        )

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()
