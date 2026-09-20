"""Text-to-SQL: question in, validated SQL and its result out.

The loop is: build a prompt from the live schema and some examples, generate
JSON, run it past the guard, execute it as the read-only role, and on failure
hand the error back to the model and try again. Self-correction is capped by
`sql.max_retries` and can be turned off entirely, which is what configuration
C0 does so the evaluation can measure what it is worth.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text
from sqlalchemy.engine import Engine

from steel_assistant.config import Settings, get_settings
from steel_assistant.db.engine import assistant_engine
from steel_assistant.llm.base import LLMClient
from steel_assistant.tools.schema_context import get_schema_context
from steel_assistant.tools.sql_guard import SQLGuardError, guard_sql

REPO_ROOT = Path(__file__).resolve().parents[3]
FEWSHOT_PATH = REPO_ROOT / "eval" / "sql_fewshot.yaml"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["sql", "explanation"],
}

SYSTEM_PROMPT = """You write PostgreSQL SELECT queries against a steel plant database.

Rules:
- Return ONE SELECT statement. Never INSERT, UPDATE, DELETE, DROP or CREATE.
- Only use tables in the `plant` schema, and always schema-qualify them.
- Use the exact literal values shown in the sample rows. They are case-sensitive:
  `Maximum_Load`, not `maximum load`.
- `ts` marks the END of each 15-minute interval.
- Write the `explanation` in the same language as the question.
- Return only JSON with the keys "sql" and "explanation"."""


@dataclass(slots=True)
class SQLAttempt:
    """One generate-validate-execute cycle, kept for the trace."""

    sql: str
    error: str | None = None
    stage: str = "generated"


@dataclass(slots=True)
class SQLResult:
    """What the tool returns to the agent."""

    sql: str | None
    explanation: str
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    exec_ms: int = 0
    attempts: list[SQLAttempt] = field(default_factory=list)
    ok: bool = True
    error: str | None = None

    def as_markdown_table(self, limit: int = 20) -> str:
        """Render the result the way the synthesis prompt consumes it."""
        if not self.columns:
            return "(no result)"
        header = " | ".join(self.columns)
        divider = " | ".join("---" for _ in self.columns)
        body = "\n".join(
            " | ".join("NULL" if value is None else str(value) for value in row)
            for row in self.rows[:limit]
        )
        suffix = (
            f"\n({self.row_count} rows total, {limit} shown)"
            if self.row_count > limit
            else f"\n({self.row_count} rows)"
        )
        return f"{header}\n{divider}\n{body}{suffix}"


def load_fewshot() -> list[dict[str, str]]:
    """Read the curated examples."""
    if not FEWSHOT_PATH.is_file():
        return []
    data = yaml.safe_load(FEWSHOT_PATH.read_text(encoding="utf-8")) or {}
    return data.get("examples", [])


def select_fewshot(
    question: str, mode: str, k: int, examples: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Pick the examples to show.

    `dynamic` embeds the question and takes the nearest examples, which costs
    one extra embedding call but keeps the prompt shorter than showing all ten.
    """
    if mode == "none" or not examples:
        return []
    if mode == "static":
        return examples
    from steel_assistant.retrieval.embedder import get_embedder

    embedder = get_embedder()
    question_vector = embedder.embed_query(question)
    example_vectors = embedder.embed_queries([e["question"] for e in examples])
    scored = sorted(
        zip(examples, example_vectors @ question_vector, strict=True),
        key=lambda pair: float(pair[1]),
        reverse=True,
    )
    return [example for example, _ in scored[:k]]


def build_messages(
    question: str,
    schema: str,
    examples: list[dict[str, str]],
    history: list[SQLAttempt],
) -> list[dict[str, str]]:
    """Assemble the prompt, including any previous failure."""
    parts = [f"Database schema:\n\n{schema}"]
    if examples:
        rendered = "\n\n".join(
            f"Question: {e['question']}\nSQL: {e['sql'].strip()}" for e in examples
        )
        parts.append(f"Examples:\n\n{rendered}")
    parts.append(f"Question: {question}")

    if history:
        last = history[-1]
        # Give the model its own rejected query back with the reason. Without
        # the query it cannot tell which part was wrong.
        parts.append(
            f"Your previous attempt was rejected.\n"
            f"SQL: {last.sql}\n"
            f"Error ({last.stage}): {last.error}\n"
            f"Fix it and return corrected JSON."
        )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def _parse_response(content: str) -> tuple[str, str]:
    """Pull sql and explanation out of the model's JSON."""
    import json

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"the model did not return valid JSON: {exc}") from exc
    sql = str(payload.get("sql") or "").strip()
    if not sql:
        raise ValueError("the model returned no SQL")
    return sql, str(payload.get("explanation") or "")


def run_sql_query(
    question: str,
    client: LLMClient,
    *,
    settings: Settings | None = None,
    engine: Engine | None = None,
    schema_context: str | None = None,
) -> SQLResult:
    """Answer a question with SQL.

    Args:
        question: the user's question, French or English.
        client: the LLM client.
        settings: configuration. Defaults to the process settings.
        engine: database engine. Defaults to the read-only assistant role.
        schema_context: override the schema description, for tests.

    Returns:
        The query, its rows, and the attempts it took.
    """
    settings = settings or get_settings()
    engine = engine or assistant_engine()
    schema = schema_context if schema_context is not None else get_schema_context()
    examples = select_fewshot(
        question, settings.sql.fewshot, settings.sql.fewshot_k, load_fewshot()
    )

    attempts: list[SQLAttempt] = []
    max_attempts = 1 + settings.sql.max_retries
    explanation = ""

    for _ in range(max_attempts):
        messages = build_messages(question, schema, examples, attempts)
        response = client.chat(
            messages,
            model=settings.llm.sql_model,
            response_format=RESPONSE_SCHEMA,
            temperature=0.0,
        )

        try:
            raw_sql, explanation = _parse_response(response.content)
        except ValueError as exc:
            attempts.append(SQLAttempt(sql=response.content[:200], error=str(exc), stage="parse"))
            continue

        try:
            guarded = guard_sql(
                raw_sql,
                allowed_schemas=tuple(settings.sql.allowed_schemas),
                default_limit=settings.sql.default_limit,
            )
        except SQLGuardError as exc:
            attempts.append(SQLAttempt(sql=raw_sql, error=str(exc), stage="guard"))
            continue

        started = time.perf_counter()
        try:
            with engine.connect() as conn:
                result = conn.execute(text(guarded.sql))
                columns = list(result.keys())
                rows = [tuple(row) for row in result.fetchall()]
        except Exception as exc:  # noqa: BLE001 - the DB error text goes back to the model
            attempts.append(SQLAttempt(sql=guarded.sql, error=str(exc)[:300], stage="execute"))
            continue
        exec_ms = int((time.perf_counter() - started) * 1000)

        attempts.append(SQLAttempt(sql=guarded.sql, stage="executed"))
        shown = settings.sql.max_rows_returned
        return SQLResult(
            sql=guarded.sql,
            explanation=explanation,
            columns=columns,
            rows=rows[:shown],
            row_count=len(rows),
            truncated=len(rows) > shown,
            exec_ms=exec_ms,
            attempts=attempts,
            ok=True,
        )

    last = attempts[-1] if attempts else None
    return SQLResult(
        sql=last.sql if last else None,
        explanation=explanation,
        attempts=attempts,
        ok=False,
        error=(
            f"failed after {len(attempts)} attempt(s); last error ({last.stage}): {last.error}"
            if last
            else "no attempt was made"
        ),
    )


def sql_tool_schema() -> dict[str, Any]:
    """The tool definition passed to a model in tool-calling mode."""
    return {
        "type": "function",
        "function": {
            "name": "sql_query",
            "description": (
                "Query the steel plant database: energy readings, plate "
                "inspections, maintenance events, production lines, shifts and "
                "fault types. Use for counts, sums, averages, rankings and "
                "anything time-based."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to answer with SQL.",
                    }
                },
                "required": ["question"],
            },
        },
    }
