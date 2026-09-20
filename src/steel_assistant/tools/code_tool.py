"""search_code: retrieval over the legacy analytics codebase.

Same shape as search_docs, but citations carry a line range, so an answer
points at `kpi_energy.py:L12-L38` rather than at a file. The line numbers come
from the AST chunker and are verified by a round-trip test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from steel_assistant.retrieval.search import SearchHit, hybrid_search


@dataclass(slots=True)
class CodeHit:
    """One cited span of source."""

    path: str
    symbol: str | None
    start_line: int | None
    end_line: int | None
    content: str
    score: float
    kind: str | None = None

    def citation(self) -> str:
        """`kpi_energy.py:L12-L38`."""
        if self.start_line is None:
            return self.path
        return f"{self.path}:L{self.start_line}-L{self.end_line}"


@dataclass(slots=True)
class CodeResult:
    """What the tool returns to the agent."""

    query: str
    hits: list[CodeHit] = field(default_factory=list)
    ok: bool = True
    error: str | None = None

    def as_prompt_context(self, max_chars: int = 1200) -> str:
        """Render the hits for the synthesis prompt, fenced as code."""
        if not self.hits:
            return "(no code matched)"
        blocks = []
        for hit in self.hits:
            language = "sql" if hit.path.endswith(".sql") else "python"
            symbol = f" ({hit.symbol})" if hit.symbol else ""
            blocks.append(
                f"--- SOURCE {hit.citation()}{symbol} ---\n"
                f"```{language}\n{hit.content[:max_chars]}\n```"
            )
        return "\n\n".join(blocks)


def _to_code_hit(hit: SearchHit) -> CodeHit:
    """Adapt a raw search hit."""
    return CodeHit(
        path=hit.source_id,
        symbol=hit.section,
        start_line=hit.start_line,
        end_line=hit.end_line,
        content=hit.content,
        score=hit.score,
        kind=(hit.metadata or {}).get("kind"),
    )


def search_code(
    query: str,
    *,
    k: int | None = None,
    path: str | None = None,
    **search_kwargs: Any,
) -> CodeResult:
    """Retrieve source spans relevant to a query.

    Args:
        query: what to look for.
        k: how many spans to return.
        path: restrict to one file, e.g. 'kpi_energy.py'.
        **search_kwargs: passed through to hybrid_search.

    Returns:
        The matching spans, best first.
    """
    try:
        hits = hybrid_search(query, "code", k=k, **search_kwargs)
    except Exception as exc:  # noqa: BLE001 - a retrieval failure is reported, not raised
        return CodeResult(query=query, ok=False, error=str(exc))
    if path:
        hits = [hit for hit in hits if hit.source_id == path]
    return CodeResult(query=query, hits=[_to_code_hit(hit) for hit in hits])


def code_tool_schema() -> dict[str, Any]:
    """The tool definition passed to a model in tool-calling mode."""
    return {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "Search the plant's legacy analytics code: KPI formulas, OEE, "
                "MTTR and MTBF, quality-hold rules, shift aggregation, the old "
                "ETL loader and named SQL queries. Use when the question is "
                "about how something is calculated or implemented."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for."},
                    "path": {
                        "type": "string",
                        "description": "Optional: restrict to one file name.",
                    },
                },
                "required": ["query"],
            },
        },
    }
