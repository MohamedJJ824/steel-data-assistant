"""LangGraph orchestration.

Two modes, both built here so the evaluation can compare them:

* **router** — one classification call, then the tools that category implies.
  Predictable, cheap, and reliable with a small local model, which is why it is
  the default.
* **tool_calling** — the model drives, choosing tools until it has enough. More
  flexible, but it depends on the model's tool-calling being good enough, which
  is exactly the thing worth measuring rather than assuming.

Both converge on the same synthesis node, so answers are formatted and grounded
identically and the comparison is about routing, not about presentation.
"""

from __future__ import annotations

import json
import time
from typing import Any

from langgraph.graph import END, StateGraph

from steel_assistant.agent.grounding import check_grounding
from steel_assistant.agent.prompts import (
    PLANNER_SYSTEM,
    REFUSAL_SYSTEM,
    ROUTER_SCHEMA,
    ROUTER_SYSTEM,
    SYNTHESIS_SYSTEM,
    synthesis_user_prompt,
)
from steel_assistant.agent.state import AgentState, Source, ToolCallRecord
from steel_assistant.config import Settings, get_settings
from steel_assistant.llm.base import LLMClient
from steel_assistant.tools.code_tool import code_tool_schema, search_code
from steel_assistant.tools.docs_tool import docs_tool_schema, search_docs
from steel_assistant.tools.sql_tool import run_sql_query, sql_tool_schema

# Accented characters and common function words are enough to tell the two
# languages apart for a one-sentence question, and it costs no LLM call.
_FRENCH_MARKERS = (
    "é",
    "è",
    "ê",
    "à",
    "ù",
    "ç",
    "ô",
    "î",
    " le ",
    " la ",
    " les ",
    " des ",
    " du ",
    " une ",
    " quel",
    " quelle",
    " combien",
    " pourquoi",
    " comment ",
    " est-ce",
    " qui ",
    " sur la ",
)


def detect_language(question: str) -> str:
    """Return 'fr' or 'en' for a question."""
    padded = f" {question.lower()} "
    return "fr" if any(marker in padded for marker in _FRENCH_MARKERS) else "en"


def _record(
    state: AgentState,
    tool: str,
    payload: dict[str, Any],
    started: float,
    *,
    ok: bool,
    summary: str = "",
    error: str | None = None,
) -> None:
    """Append a tool call to the trace."""
    state.setdefault("tool_calls", []).append(
        ToolCallRecord(
            tool=tool,
            input=payload,
            latency_ms=int((time.perf_counter() - started) * 1000),
            ok=ok,
            summary=summary,
            error=error,
        )
    )


# ------------------------------------------------------------------- tools --


def _call_sql(state: AgentState, client: LLMClient, settings: Settings) -> None:
    """Run the SQL tool and fold its output into the state."""
    started = time.perf_counter()
    result = run_sql_query(state["question"], client, settings=settings)
    state["sql_result"] = result

    if result.ok and result.sql:
        rendered = (
            f"--- SOURCE SQL ---\nQuery:\n{result.sql}\n\nResult:\n{result.as_markdown_table()}"
        )
        state.setdefault("tool_outputs", []).append(rendered)
        state.setdefault("sources", []).append(
            Source(type="sql", id="sql_query", snippet=result.sql)
        )
        _record(
            state,
            "sql_query",
            {"question": state["question"]},
            started,
            ok=True,
            summary=f"{result.row_count} rows in {result.exec_ms} ms",
        )
    else:
        _record(
            state,
            "sql_query",
            {"question": state["question"]},
            started,
            ok=False,
            error=result.error,
        )
        state.setdefault("tool_outputs", []).append(
            f"--- SOURCE SQL ---\nThe query could not be run: {result.error}"
        )


def _call_docs(state: AgentState, query: str | None = None, **kwargs: Any) -> None:
    """Run the documents tool and fold its output into the state."""
    started = time.perf_counter()
    question = query or state["question"]
    result = search_docs(question, **kwargs)
    if result.ok and result.hits:
        state.setdefault("tool_outputs", []).append(result.as_prompt_context())
        for hit in result.hits:
            state.setdefault("sources", []).append(
                Source(
                    type="doc",
                    id=hit.doc_id,
                    section=hit.section,
                    snippet=hit.content[:300],
                )
            )
        _record(
            state,
            "search_docs",
            {"query": question},
            started,
            ok=True,
            summary=f"{len(result.hits)} sections",
        )
    else:
        _record(
            state,
            "search_docs",
            {"query": question},
            started,
            ok=False,
            error=result.error or "no match",
        )


def _call_code(state: AgentState, query: str | None = None, **kwargs: Any) -> None:
    """Run the code tool and fold its output into the state."""
    started = time.perf_counter()
    question = query or state["question"]
    result = search_code(question, **kwargs)
    if result.ok and result.hits:
        state.setdefault("tool_outputs", []).append(result.as_prompt_context())
        for hit in result.hits:
            state.setdefault("sources", []).append(
                Source(
                    type="code",
                    id=hit.path,
                    section=hit.symbol,
                    snippet=hit.content[:300],
                    start_line=hit.start_line,
                    end_line=hit.end_line,
                )
            )
        _record(
            state,
            "search_code",
            {"query": question},
            started,
            ok=True,
            summary=f"{len(result.hits)} spans",
        )
    else:
        _record(
            state,
            "search_code",
            {"query": question},
            started,
            ok=False,
            error=result.error or "no match",
        )


# ------------------------------------------------------------------- nodes --


def make_classify_node(client: LLMClient, settings: Settings):  # noqa: ANN201
    """Node: detect language, then classify the question."""

    def classify(state: AgentState) -> AgentState:
        state["language"] = detect_language(state["question"])
        response = client.chat(
            [
                {"role": "system", "content": ROUTER_SYSTEM},
                {"role": "user", "content": state["question"]},
            ],
            model=settings.llm.agent_model,
            response_format=ROUTER_SCHEMA,
            temperature=0.0,
        )
        try:
            state["category"] = json.loads(response.content).get("category", "multi")
        except json.JSONDecodeError:
            # A malformed classification should widen the search, not fail the
            # request: multi runs every tool and lets synthesis decide.
            state["category"] = "multi"
        return state

    return classify


def make_tools_node(client: LLMClient, settings: Settings):  # noqa: ANN201
    """Node: run the tools the category implies."""

    def run_tools(state: AgentState) -> AgentState:
        category = state.get("category") or "multi"
        if category in ("sql", "multi"):
            _call_sql(state, client, settings)
        if category in ("docs", "multi"):
            _call_docs(state)
        if category in ("code", "multi"):
            _call_code(state)
        return state

    return run_tools


def make_tool_calling_node(client: LLMClient, settings: Settings):  # noqa: ANN201
    """Node: let the model choose tools, up to agent.max_tool_calls."""
    tools = [sql_tool_schema(), docs_tool_schema(), code_tool_schema()]
    dispatch = {"sql_query": _call_sql, "search_docs": _call_docs, "search_code": _call_code}

    def plan(state: AgentState) -> AgentState:
        state["language"] = detect_language(state["question"])
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": state["question"]},
        ]
        called: set[str] = set()

        for _ in range(settings.agent.max_tool_calls):
            response = client.chat(
                messages, model=settings.llm.agent_model, tools=tools, temperature=0.0
            )
            if not response.tool_calls:
                break
            for call in response.tool_calls:
                handler = dispatch.get(call.name)
                # Repeating a tool with the same arguments adds latency and no
                # information, and small models loop readily.
                signature = f"{call.name}:{json.dumps(call.arguments, sort_keys=True)}"
                if handler is None or signature in called:
                    continue
                called.add(signature)
                if call.name == "sql_query":
                    _call_sql(state, client, settings)
                else:
                    handler(state, query=call.arguments.get("query"))
            messages.append(
                {"role": "assistant", "content": response.content or "(tool calls issued)"}
            )
            messages.append(
                {
                    "role": "user",
                    "content": "Call another tool if you still need one, otherwise stop.",
                }
            )

        if not state.get("tool_outputs"):
            # The model declined to use any tool. Fall back to running all of
            # them rather than synthesising from nothing.
            _call_sql(state, client, settings)
            _call_docs(state)
            _call_code(state)
        return state

    return plan


def make_synthesis_node(client: LLMClient, settings: Settings):  # noqa: ANN201
    """Node: write the answer, then check its numbers."""

    def synthesise(state: AgentState) -> AgentState:
        outputs = state.get("tool_outputs", [])
        response = client.chat(
            [
                {"role": "system", "content": SYNTHESIS_SYSTEM},
                {
                    "role": "user",
                    "content": synthesis_user_prompt(state["question"], outputs),
                },
            ],
            model=settings.llm.agent_model,
            temperature=0.0,
        )
        state["answer"] = response.content.strip()
        grounding = check_grounding(state["answer"], outputs)
        state["grounding"] = {
            "numbers_checked": grounding.numbers_checked,
            "numbers_grounded": grounding.numbers_grounded,
            "ungrounded": grounding.ungrounded,
        }
        return state

    return synthesise


def make_refusal_node(client: LLMClient, settings: Settings):  # noqa: ANN201
    """Node: decline an out-of-scope question."""

    def refuse(state: AgentState) -> AgentState:
        response = client.chat(
            [
                {"role": "system", "content": REFUSAL_SYSTEM},
                {"role": "user", "content": state["question"]},
            ],
            model=settings.llm.agent_model,
            temperature=0.0,
        )
        state["answer"] = response.content.strip()
        state["grounding"] = {"numbers_checked": 0, "numbers_grounded": 0, "ungrounded": []}
        return state

    return refuse


# ------------------------------------------------------------------- graph --


def build_graph(client: LLMClient, settings: Settings | None = None):  # noqa: ANN201
    """Compile the agent graph for the configured mode."""
    settings = settings or get_settings()

    graph = StateGraph(AgentState)
    graph.add_node("synthesise", make_synthesis_node(client, settings))
    graph.add_node("refuse", make_refusal_node(client, settings))

    if settings.agent.mode == "tool_calling":
        graph.add_node("plan", make_tool_calling_node(client, settings))
        graph.set_entry_point("plan")
        graph.add_edge("plan", "synthesise")
    else:
        graph.add_node("classify", make_classify_node(client, settings))
        graph.add_node("run_tools", make_tools_node(client, settings))
        graph.set_entry_point("classify")
        graph.add_conditional_edges(
            "classify",
            lambda state: "refuse" if state.get("category") == "out_of_scope" else "run_tools",
            {"refuse": "refuse", "run_tools": "run_tools"},
        )
        graph.add_edge("run_tools", "synthesise")

    graph.add_edge("synthesise", END)
    graph.add_edge("refuse", END)
    return graph.compile()


def answer_question(
    question: str,
    client: LLMClient,
    settings: Settings | None = None,
) -> AgentState:
    """Run one question end to end and return the final state."""
    settings = settings or get_settings()
    graph = build_graph(client, settings)
    initial: AgentState = {
        "question": question,
        "tool_calls": [],
        "tool_outputs": [],
        "sources": [],
    }
    return graph.invoke(initial)
