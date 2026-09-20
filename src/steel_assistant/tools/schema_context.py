"""Builds the schema description the text-to-SQL prompt is grounded in.

Read straight from the live database rather than kept as a hand-maintained
string, so it cannot drift from the tables it describes. The FR/EN `COMMENT ON`
text written in milestone 1 is the point: it tells the model that `ts` marks the
*end* of an interval and that power factors are percentages, which no amount of
column-name inference would reveal.

Cached per process, because it costs several queries and never changes while
the service is running.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from steel_assistant.config import get_settings
from steel_assistant.db.engine import app_engine

SAMPLE_ROWS = 3


@dataclass(slots=True)
class ColumnInfo:
    """One column, with its documentation."""

    name: str
    data_type: str
    nullable: bool
    comment: str | None


@dataclass(slots=True)
class TableInfo:
    """One table, its columns, keys and sample rows."""

    schema: str
    name: str
    comment: str | None
    columns: list[ColumnInfo]
    primary_key: list[str]
    foreign_keys: list[tuple[str, str, str]]
    sample_rows: list[tuple]

    @property
    def qualified(self) -> str:
        """`schema.table`."""
        return f"{self.schema}.{self.name}"


def _fetch_tables(conn: object, schema: str) -> list[str]:
    return list(
        conn.execute(  # type: ignore[attr-defined]
            text("SELECT tablename FROM pg_tables WHERE schemaname = :schema ORDER BY tablename"),
            {"schema": schema},
        ).scalars()
    )


def _fetch_columns(conn: object, schema: str, table: str) -> list[ColumnInfo]:
    rows = conn.execute(  # type: ignore[attr-defined]
        text(
            """
            SELECT c.column_name, c.data_type, c.is_nullable,
                   col_description(pc.oid, c.ordinal_position) AS comment
            FROM information_schema.columns c
            JOIN pg_class pc ON pc.relname = c.table_name
            JOIN pg_namespace pn ON pn.oid = pc.relnamespace AND pn.nspname = c.table_schema
            WHERE c.table_schema = :schema AND c.table_name = :table
            ORDER BY c.ordinal_position
            """
        ),
        {"schema": schema, "table": table},
    ).all()
    return [
        ColumnInfo(name=r[0], data_type=r[1], nullable=r[2] == "YES", comment=r[3]) for r in rows
    ]


def _fetch_keys(
    conn: object, schema: str, table: str
) -> tuple[list[str], list[tuple[str, str, str]]]:
    primary = list(
        conn.execute(  # type: ignore[attr-defined]
            text(
                """
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = (:qualified)::regclass AND i.indisprimary
                """
            ),
            {"qualified": f"{schema}.{table}"},
        ).scalars()
    )
    foreign = [
        (r[0], r[1], r[2])
        for r in conn.execute(  # type: ignore[attr-defined]
            text(
                """
                SELECT kcu.column_name,
                       ccu.table_schema || '.' || ccu.table_name AS references_table,
                       ccu.column_name AS references_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON kcu.constraint_name = tc.constraint_name
                 AND kcu.table_schema = tc.table_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = :schema AND tc.table_name = :table
                """
            ),
            {"schema": schema, "table": table},
        ).all()
    ]
    return primary, foreign


def _fetch_samples(conn: object, schema: str, table: str, columns: list[ColumnInfo]) -> list[tuple]:
    """A few real rows, so the model sees actual value formats.

    This is what stops the model guessing `load_type = 'maximum load'` when the
    stored value is `Maximum_Load` — a mistake it made on the very first probe
    of this project, before any schema context existed.
    """
    names = ", ".join(f'"{c.name}"' for c in columns[:12])
    rows = conn.execute(  # type: ignore[attr-defined]
        text(f"SELECT {names} FROM {schema}.{table} LIMIT {SAMPLE_ROWS}")
    ).all()
    return [tuple(row) for row in rows]


def build_schema_info(schema: str = "plant", engine: Engine | None = None) -> list[TableInfo]:
    """Read one schema's structure, documentation and sample rows."""
    engine = engine or app_engine()
    tables: list[TableInfo] = []
    with engine.connect() as conn:
        for name in _fetch_tables(conn, schema):
            columns = _fetch_columns(conn, schema, name)
            primary, foreign = _fetch_keys(conn, schema, name)
            comment = conn.execute(
                text("SELECT obj_description((:q)::regclass)"),
                {"q": f"{schema}.{name}"},
            ).scalar_one_or_none()
            tables.append(
                TableInfo(
                    schema=schema,
                    name=name,
                    comment=comment,
                    columns=columns,
                    primary_key=primary,
                    foreign_keys=foreign,
                    sample_rows=_fetch_samples(conn, schema, name, columns),
                )
            )
    return tables


def render_schema_context(tables: list[TableInfo], *, max_sample_chars: int = 90) -> str:
    """Render the schema as the compact text the prompt embeds."""
    blocks: list[str] = []
    for table in tables:
        lines = [f"TABLE {table.qualified}"]
        if table.comment:
            lines.append(f"  -- {table.comment}")
        for column in table.columns:
            flags = []
            if column.name in table.primary_key:
                flags.append("PK")
            if not column.nullable:
                flags.append("NOT NULL")
            suffix = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"  {column.name} {column.data_type}{suffix}")
            if column.comment:
                lines.append(f"      -- {column.comment}")
        for column_name, ref_table, ref_column in table.foreign_keys:
            lines.append(f"  FOREIGN KEY {column_name} -> {ref_table}.{ref_column}")
        if table.sample_rows:
            lines.append("  Sample rows:")
            for row in table.sample_rows:
                rendered = ", ".join(str(value) for value in row)
                if len(rendered) > max_sample_chars:
                    rendered = rendered[:max_sample_chars] + "..."
                lines.append(f"    ({rendered})")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


@functools.lru_cache(maxsize=1)
def get_schema_context() -> str:
    """The rendered schema context, built once per process."""
    schema = get_settings().sql.allowed_schemas[0]
    return render_schema_context(build_schema_info(schema))
