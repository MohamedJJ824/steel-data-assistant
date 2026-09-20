"""Shared dependencies: authentication and the process-wide LLM client."""

from __future__ import annotations

import functools

from fastapi import Header, HTTPException, status

from steel_assistant.config import get_settings
from steel_assistant.llm.base import LLMClient
from steel_assistant.llm.factory import build_llm_client


@functools.lru_cache(maxsize=1)
def get_client() -> LLMClient:
    """The LLM client, built once so the model stays resident."""
    return build_llm_client()


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reject a request without the configured API key.

    A single static key is enough for a proof of concept; the README is explicit
    that real deployment would need SSO and per-table access control.
    """
    expected = get_settings().api.key.get_secret_value()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SDA_API__KEY is not configured on the server",
        )
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing X-API-Key"
        )
