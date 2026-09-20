"""The state the agent graph carries between nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

Category = Literal["sql", "docs", "code", "multi", "out_of_scope"]


@dataclass(slots=True)
class ToolCallRecord:
    """One tool invocation, for the trace the API returns."""

    tool: str
    input: dict[str, Any]
    latency_ms: int
    ok: bool
    summary: str = ""
    error: str | None = None


@dataclass(slots=True)
class Source:
    """One piece of evidence behind an answer."""

    type: Literal["doc", "code", "sql"]
    id: str
    section: str | None = None
    snippet: str = ""
    start_line: int | None = None
    end_line: int | None = None


class AgentState(TypedDict, total=False):
    """Graph state.

    A TypedDict rather than a dataclass because LangGraph merges partial
    updates returned by each node into this mapping.
    """

    question: str
    language: str
    category: Category | None
    tool_calls: list[ToolCallRecord]
    tool_outputs: list[str]
    sources: list[Source]
    sql_result: Any
    answer: str
    grounding: dict[str, Any]
    error: str | None
    options: dict[str, Any]
