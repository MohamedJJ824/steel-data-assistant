"""AST-level validation of generated SQL.

This is the second of the two layers that keep the agent read-only. The first
is the `assistant_ro` role, which holds `SELECT` on schema `plant` and nothing
else. Neither layer is trusted alone: the role stops anything the guard misses,
and the guard stops things the role permits — reading `pg_catalog`, calling
`pg_sleep`, or scanning a whole table with no `LIMIT`.

Validation walks the parsed tree rather than matching text. A blocklist of
strings is defeated by `/**/`, by case, by unicode escapes and by string
concatenation; a parser sees what the database will see.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

DIALECT = "postgres"

# Schemas the agent may read. Anything else — rag, app, pg_catalog,
# information_schema — is rejected even though the role already blocks most of
# it, because pg_catalog is readable by every role and cannot practically be
# revoked.
DEFAULT_ALLOWED_SCHEMAS = ("plant",)

# Functions that read the filesystem, sleep, reach the network or touch large
# objects. `pg_sleep` alone would let a generated query hold a connection for
# as long as it liked, and the role's 5s statement_timeout is a backstop, not a
# reason to allow it.
BLOCKED_FUNCTIONS = frozenset(
    {
        "pg_sleep",
        "pg_sleep_for",
        "pg_sleep_until",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "pg_logdir_ls",
        "lo_import",
        "lo_export",
        "lo_get",
        "dblink",
        "dblink_exec",
        "dblink_connect",
        "query_to_xml",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "pg_rotate_logfile",
        "set_config",
        "current_setting",
        "pg_read_server_files",
        "copy",
    }
)

# Every statement type that is not a read.
WRITE_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Merge,
)


class SQLGuardError(Exception):
    """Raised when a statement is rejected. The message goes back to the model."""


@dataclass(slots=True)
class GuardResult:
    """Outcome of validating one statement."""

    sql: str
    """The SQL to execute, with a LIMIT added if one was missing."""

    tables: list[str] = field(default_factory=list)
    """Qualified table names the statement reads."""

    limit_added: bool = False
    """True when the guard injected a LIMIT."""

    is_aggregate: bool = False
    """True when the statement is a bare aggregate, which needs no LIMIT."""


def _qualified_name(table: exp.Table) -> str:
    """`schema.table` for a table node, or just the name when unqualified."""
    schema = table.text("db")
    name = table.name
    return f"{schema}.{name}" if schema else name


def _is_bare_aggregate(statement: exp.Expression) -> bool:
    """True when the query returns one row per group and cannot run away.

    A `SELECT count(*) FROM t` returns exactly one row, so a LIMIT adds nothing.
    A `GROUP BY` can still return many rows, so it does not count.
    """
    select = statement.find(exp.Select)
    if select is None:
        return False
    if select.args.get("group"):
        return False
    expressions = select.expressions
    if not expressions:
        return False
    return all(isinstance(projection.unalias(), exp.AggFunc) for projection in expressions)


def _check_no_writes(statement: exp.Expression) -> None:
    """Reject anything that is not a read."""
    if isinstance(statement, WRITE_EXPRESSIONS):
        raise SQLGuardError(
            f"only SELECT statements are allowed, got {type(statement).__name__.upper()}"
        )
    for node in statement.walk():
        if isinstance(node, WRITE_EXPRESSIONS):
            raise SQLGuardError(
                f"only SELECT statements are allowed, found a nested {type(node).__name__.upper()}"
            )


def _check_root_is_select(statement: exp.Expression) -> None:
    """The root must be a SELECT, or a WITH whose body and CTEs are all SELECTs."""
    if isinstance(statement, exp.Select):
        return
    if isinstance(statement, exp.Subquery) and statement.find(exp.Select):
        return
    if isinstance(statement, exp.Union | exp.Except | exp.Intersect):
        return
    raise SQLGuardError(f"the statement must be a SELECT, got {type(statement).__name__.upper()}")


def _check_ctes_are_selects(statement: exp.Expression) -> None:
    """Every CTE must itself be a read.

    Postgres allows a data-modifying CTE (`WITH x AS (DELETE ... RETURNING ...)`),
    which would otherwise sail past a check that only looks at the root.
    """
    for cte in statement.find_all(exp.CTE):
        inner = cte.this
        if isinstance(inner, WRITE_EXPRESSIONS):
            raise SQLGuardError(
                f"CTE '{cte.alias}' must be a SELECT, got {type(inner).__name__.upper()}"
            )


def _check_no_into(statement: exp.Expression) -> None:
    """Reject SELECT ... INTO, which creates a table."""
    if statement.find(exp.Into) is not None:
        raise SQLGuardError("SELECT ... INTO is not allowed: it writes a new table")


def _check_no_locking(statement: exp.Expression) -> None:
    """Reject FOR UPDATE and friends, which take row locks."""
    if statement.find(exp.Lock) is not None:
        raise SQLGuardError("locking clauses such as FOR UPDATE are not allowed")


def _check_functions(statement: exp.Expression) -> None:
    """Reject blocked functions and any pg_* administrative function."""
    for node in statement.find_all(exp.Anonymous, exp.Func):
        name = (node.name or "").lower() if isinstance(node, exp.Anonymous) else ""
        if not name:
            name = node.sql_name().lower() if hasattr(node, "sql_name") else ""
        if not name:
            continue
        if name in BLOCKED_FUNCTIONS:
            raise SQLGuardError(f"function '{name}' is not allowed")
        # Catch-all for the admin surface: no legitimate analytical query needs
        # a pg_* function, and enumerating them all would go stale.
        if name.startswith("pg_") and name not in {"pg_typeof"}:
            raise SQLGuardError(f"administrative function '{name}' is not allowed")


def _check_tables(statement: exp.Expression, allowed_schemas: tuple[str, ...]) -> list[str]:
    """Every table must live in an allowed schema. Returns the names found."""
    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    tables: list[str] = []

    for table in statement.find_all(exp.Table):
        name = table.name
        schema = table.text("db")

        # A reference to a CTE defined in this same statement is not a real table.
        if not schema and name.lower() in cte_names:
            continue

        if not schema:
            raise SQLGuardError(
                f"table '{name}' is not schema-qualified; write '{allowed_schemas[0]}.{name}'"
            )
        if schema.lower() not in allowed_schemas:
            raise SQLGuardError(
                f"schema '{schema}' is not readable; allowed: {', '.join(allowed_schemas)}"
            )
        tables.append(_qualified_name(table))

    if not tables:
        raise SQLGuardError("the statement reads no table in an allowed schema")
    return sorted(set(tables))


def guard_sql(
    sql: str,
    *,
    allowed_schemas: tuple[str, ...] | list[str] = DEFAULT_ALLOWED_SCHEMAS,
    default_limit: int = 200,
) -> GuardResult:
    """Validate generated SQL and return it ready to execute.

    Args:
        sql: the statement the model produced.
        allowed_schemas: schemas the agent may read.
        default_limit: LIMIT injected when the query has none and is not a
            bare aggregate.

    Returns:
        The validated statement, its tables, and whether a LIMIT was added.

    Raises:
        SQLGuardError: with a message written to be fed back to the model for
            self-correction.
    """
    allowed = tuple(schema.lower() for schema in allowed_schemas)

    if not sql or not sql.strip():
        raise SQLGuardError("the statement is empty")

    try:
        statements = sqlglot.parse(sql, dialect=DIALECT)
    except Exception as exc:  # noqa: BLE001 - sqlglot raises several parse types
        raise SQLGuardError(f"the statement does not parse: {exc}") from exc

    statements = [statement for statement in statements if statement is not None]
    if len(statements) != 1:
        raise SQLGuardError(f"exactly one statement is allowed, got {len(statements)}")

    statement = statements[0]

    _check_no_writes(statement)
    _check_root_is_select(statement)
    _check_ctes_are_selects(statement)
    _check_no_into(statement)
    _check_no_locking(statement)
    _check_functions(statement)
    tables = _check_tables(statement, allowed)

    is_aggregate = _is_bare_aggregate(statement)
    limit_added = False
    if statement.args.get("limit") is None and not is_aggregate:
        statement = statement.limit(default_limit)
        limit_added = True

    return GuardResult(
        sql=statement.sql(dialect=DIALECT),
        tables=tables,
        limit_added=limit_added,
        is_aggregate=is_aggregate,
    )
