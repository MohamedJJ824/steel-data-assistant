"""Request and response models for the HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AskOptions(BaseModel):
    """Per-request overrides, used by the UI and the evaluation harness."""

    agent_mode: Literal["router", "tool_calling"] | None = None
    rerank: bool | None = None
    retrieval_mode: Literal["dense", "hybrid"] | None = None


class AskRequest(BaseModel):
    """A question."""

    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    options: AskOptions | None = None


class ToolCallOut(BaseModel):
    """One tool invocation in the trace."""

    tool: str
    input: dict[str, Any]
    latency_ms: int
    ok: bool
    summary: str = ""
    error: str | None = None


class SQLOut(BaseModel):
    """The SQL the agent ran and what it returned."""

    query: str
    explanation: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    exec_ms: int = 0
    attempts: int = 1


class SourceOut(BaseModel):
    """One piece of evidence."""

    type: Literal["doc", "code", "sql"]
    id: str
    section: str | None = None
    snippet: str = ""
    start_line: int | None = None
    end_line: int | None = None


class GroundingOut(BaseModel):
    """Result of the number-grounding check."""

    numbers_checked: int = 0
    numbers_grounded: int = 0
    ungrounded: list[str] = Field(default_factory=list)


class AskResponse(BaseModel):
    """The answer, with everything needed to audit it."""

    trace_id: str
    answer: str
    language: str
    category: str | None = None
    tool_calls: list[ToolCallOut] = Field(default_factory=list)
    sql: SQLOut | None = None
    sources: list[SourceOut] = Field(default_factory=list)
    grounding: GroundingOut = Field(default_factory=GroundingOut)
    latency_ms: int = 0


class FeedbackRequest(BaseModel):
    """A thumbs up or down on an answer."""

    trace_id: str
    rating: Literal[-1, 1]
    comment: str | None = Field(default=None, max_length=2000)


class HealthResponse(BaseModel):
    """Whether the dependencies are reachable."""

    status: Literal["ok", "degraded"]
    database: bool
    llm: bool
    llm_backend: str
    agent_model: str
