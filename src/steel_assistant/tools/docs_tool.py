"""search_docs: retrieval over the French document corpus.

Thin over `hybrid_search`. Its job is to shape results into something a
synthesis prompt can cite, and to render retrieved text so that the model
treats it as data. Documents are attacker-controlled in the general case — a
procedure could contain "ignore your instructions" — so the rendering marks
them explicitly as quoted material.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from steel_assistant.retrieval.search import SearchHit, hybrid_search


@dataclass(slots=True)
class DocHit:
    """One cited document section."""

    doc_id: str
    title: str
    section: str | None
    content: str
    score: float
    doc_type: str | None = None
    line_id: str | None = None
    fault_code: str | None = None

    def citation(self) -> str:
        """`[PROC-FLT-ZSCR §Actions immédiates]`."""
        return f"[{self.doc_id} §{self.section}]" if self.section else f"[{self.doc_id}]"


@dataclass(slots=True)
class DocsResult:
    """What the tool returns to the agent."""

    query: str
    hits: list[DocHit] = field(default_factory=list)
    ok: bool = True
    error: str | None = None

    def as_prompt_context(self, max_chars: int = 1200) -> str:
        """Render the hits for the synthesis prompt.

        Each section is fenced and labelled with its citation, so the model has
        an unambiguous string to quote and a clear boundary between instruction
        and retrieved data.
        """
        if not self.hits:
            return "(no document matched)"
        blocks = []
        for hit in self.hits:
            content = hit.content[:max_chars]
            blocks.append(f"--- SOURCE {hit.citation()} (titre: {hit.title}) ---\n{content}")
        return "\n\n".join(blocks)


def _to_doc_hit(hit: SearchHit) -> DocHit:
    """Adapt a raw search hit, pulling front matter out of the metadata."""
    metadata = hit.metadata or {}
    # The section stored by the chunker is the full heading path; the leading
    # element is the document's H1, which repeats the title. Drop it so the
    # citation reads `§Actions immédiates` rather than repeating the title.
    section = hit.section
    if section and " > " in section:
        section = section.split(" > ", 1)[1]
    return DocHit(
        doc_id=hit.source_id,
        title=str(metadata.get("title", hit.source_id)),
        section=section,
        content=hit.content,
        score=hit.score,
        doc_type=metadata.get("doc_type"),
        line_id=metadata.get("line_id"),
        fault_code=metadata.get("fault_code"),
    )


def search_docs(
    query: str,
    *,
    k: int | None = None,
    doc_type: str | None = None,
    line_id: str | None = None,
    fault_code: str | None = None,
    **search_kwargs: Any,
) -> DocsResult:
    """Retrieve document sections relevant to a query.

    Args:
        query: what to look for, in any language.
        k: how many sections to return.
        doc_type: restrict to procedure, manual, maintenance_report, policy
            or reference.
        line_id: restrict to one production line.
        fault_code: restrict to one fault type.
        **search_kwargs: passed through to hybrid_search (mode, rerank...).

    Returns:
        The matching sections, best first.
    """
    filters = {
        key: value
        for key, value in (("doc_type", doc_type), ("line_id", line_id), ("fault_code", fault_code))
        if value is not None
    }
    try:
        hits = hybrid_search(query, "doc", k=k, filters=filters or None, **search_kwargs)
    except Exception as exc:  # noqa: BLE001 - a retrieval failure is reported, not raised
        return DocsResult(query=query, ok=False, error=str(exc))
    return DocsResult(query=query, hits=[_to_doc_hit(hit) for hit in hits])


def docs_tool_schema() -> dict[str, Any]:
    """The tool definition passed to a model in tool-calling mode."""
    return {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": (
                "Search the plant's French documentation: fault handling "
                "procedures, line operating manuals, maintenance reports, "
                "policies and reference material. Use for how-to questions, "
                "rules, thresholds and responsibilities."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for."},
                    "doc_type": {
                        "type": "string",
                        "enum": [
                            "procedure",
                            "manual",
                            "maintenance_report",
                            "policy",
                            "reference",
                        ],
                        "description": "Optional: restrict to one kind of document.",
                    },
                    "fault_code": {
                        "type": "string",
                        "description": "Optional: restrict to one fault code.",
                    },
                },
                "required": ["query"],
            },
        },
    }
