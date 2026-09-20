"""FastAPI service.

Every request gets a trace id that appears in the logs, in the response and in
`app.request_log`, so an answer a user disagrees with can be traced back to the
tools and the SQL that produced it. Row contents are deliberately not logged.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import text

from steel_assistant.agent.graph import answer_question
from steel_assistant.api.deps import get_client, require_api_key
from steel_assistant.api.schemas import (
    AskRequest,
    AskResponse,
    FeedbackRequest,
    GroundingOut,
    HealthResponse,
    SourceOut,
    SQLOut,
    ToolCallOut,
)
from steel_assistant.config import get_settings
from steel_assistant.db.engine import app_engine
from steel_assistant.logging import configure_logging

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201, ARG001
    """Configure logging at start-up."""
    configure_logging()
    log.info("api.start", backend=get_settings().llm.backend)
    yield


app = FastAPI(
    title="Steel Plant Data Assistant",
    description="Answers questions over the plant's SQL database, documents and code.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report whether the database and the LLM backend are reachable."""
    settings = get_settings()

    database = False
    try:
        with app_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        database = True
    except Exception as exc:  # noqa: BLE001 - health must report, never raise
        log.warning("health.database_unreachable", error=str(exc))

    llm = False
    try:
        llm = get_client().is_available()
    except Exception as exc:  # noqa: BLE001
        log.warning("health.llm_unreachable", error=str(exc))

    return HealthResponse(
        status="ok" if (database and llm) else "degraded",
        database=database,
        llm=llm,
        llm_backend=settings.llm.backend,
        agent_model=settings.llm.agent_model,
    )


def _log_request(trace_id: str, request: AskRequest, state: dict, latency_ms: int) -> None:
    """Record the request. Never records returned rows."""
    try:
        with app_engine().begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO app.request_log "
                    "(trace_id, session_id, question, language, agent_mode, "
                    " tools_used, latency_ms, ok, error) "
                    "VALUES (CAST(:trace_id AS uuid), :session_id, :question, "
                    " :language, :agent_mode, :tools_used, :latency_ms, :ok, :error)"
                ),
                {
                    "trace_id": trace_id,
                    "session_id": request.session_id,
                    "question": request.question,
                    "language": state.get("language"),
                    "agent_mode": get_settings().agent.mode,
                    "tools_used": [tc.tool for tc in state.get("tool_calls", [])],
                    "latency_ms": latency_ms,
                    "ok": bool(state.get("answer")),
                    "error": state.get("error"),
                },
            )
    except Exception as exc:  # noqa: BLE001 - logging must not fail a request
        log.warning("request_log.failed", trace_id=trace_id, error=str(exc))


def _build_sql_out(state: dict) -> SQLOut | None:
    """Shape the SQL result for the response, if the SQL tool ran."""
    result = state.get("sql_result")
    if result is None or not getattr(result, "ok", False) or not result.sql:
        return None
    return SQLOut(
        query=result.sql,
        explanation=result.explanation,
        columns=result.columns,
        rows=[list(row) for row in result.rows],
        row_count=result.row_count,
        truncated=result.truncated,
        exec_ms=result.exec_ms,
        attempts=len(result.attempts),
    )


@app.post("/v1/ask", response_model=AskResponse, dependencies=[Depends(require_api_key)])
async def ask(request: AskRequest) -> AskResponse:
    """Answer a question about the plant."""
    trace_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(trace_id=trace_id)
    settings = get_settings()

    if request.options:
        # Per-request overrides. A copy, so one request cannot change the
        # configuration the next one sees.
        settings = settings.model_copy(deep=True)
        if request.options.agent_mode:
            settings.agent.mode = request.options.agent_mode
        if request.options.rerank is not None:
            settings.retrieval.rerank = request.options.rerank
        if request.options.retrieval_mode:
            settings.retrieval.mode = request.options.retrieval_mode

    started = time.perf_counter()
    log.info("ask.start", question_chars=len(request.question))
    try:
        state = answer_question(request.question, get_client(), settings)
    except Exception as exc:
        log.exception("ask.failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"the agent failed: {exc}",
        ) from exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    grounding = state.get("grounding") or {}
    log.info(
        "ask.done",
        latency_ms=latency_ms,
        category=state.get("category"),
        tools=[tc.tool for tc in state.get("tool_calls", [])],
        numbers_grounded=grounding.get("numbers_grounded"),
        numbers_checked=grounding.get("numbers_checked"),
    )
    _log_request(trace_id, request, state, latency_ms)
    structlog.contextvars.clear_contextvars()

    return AskResponse(
        trace_id=trace_id,
        answer=state.get("answer", ""),
        language=state.get("language", "en"),
        category=state.get("category"),
        tool_calls=[
            ToolCallOut(
                tool=tc.tool,
                input=tc.input,
                latency_ms=tc.latency_ms,
                ok=tc.ok,
                summary=tc.summary,
                error=tc.error,
            )
            for tc in state.get("tool_calls", [])
        ],
        sql=_build_sql_out(state),
        sources=[
            SourceOut(
                type=s.type,
                id=s.id,
                section=s.section,
                snippet=s.snippet,
                start_line=s.start_line,
                end_line=s.end_line,
            )
            for s in state.get("sources", [])
        ],
        grounding=GroundingOut(**grounding) if grounding else GroundingOut(),
        latency_ms=latency_ms,
    )


@app.post("/v1/feedback", status_code=201, dependencies=[Depends(require_api_key)])
async def feedback(request: FeedbackRequest) -> dict[str, str]:
    """Record a thumbs up or down against a trace id."""
    try:
        with app_engine().begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM app.request_log WHERE trace_id = CAST(:t AS uuid)"),
                {"t": request.trace_id},
            ).scalar_one_or_none()
            if exists is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"unknown trace_id {request.trace_id}",
                )
            conn.execute(
                text(
                    "INSERT INTO app.feedback (trace_id, rating, comment) "
                    "VALUES (CAST(:t AS uuid), :rating, :comment)"
                ),
                {"t": request.trace_id, "rating": request.rating, "comment": request.comment},
            )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("feedback.failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    return {"status": "recorded"}


@app.get("/v1/sources/doc/{doc_id}", dependencies=[Depends(require_api_key)])
async def get_document(doc_id: str) -> dict[str, Any]:
    """Return a whole document, so the UI can show a citation in context."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "corpus" / "docs" / f"{doc_id}.md"
    # doc_id comes from the URL: resolve and confirm it stayed inside the
    # corpus directory, so `../../etc/passwd` cannot escape.
    try:
        resolved = path.resolve()
        resolved.relative_to((repo_root / "corpus" / "docs").resolve())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bad doc_id") from exc
    if not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no document {doc_id}")
    return {"doc_id": doc_id, "content": resolved.read_text(encoding="utf-8")}


@app.get("/v1/sources/code", dependencies=[Depends(require_api_key)])
async def get_code(path: str = Query(min_length=1)) -> dict[str, Any]:
    """Return a whole source file, so the UI can show cited lines in context."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    base = (repo_root / "corpus" / "legacy_code").resolve()
    try:
        resolved = (base / path).resolve()
        resolved.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bad path") from exc
    if not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no file {path}")
    return {"path": path, "content": resolved.read_text(encoding="utf-8")}
