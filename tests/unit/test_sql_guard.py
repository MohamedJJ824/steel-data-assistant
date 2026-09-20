"""SQL guard tests.

The guard is the second of the two layers keeping the agent read-only, so the
rejection cases here are the security claim. Each must-reject case is something
a model could plausibly emit, either by mistake or because a retrieved document
told it to.
"""

import pytest

from steel_assistant.tools.sql_guard import SQLGuardError, guard_sql

# --------------------------------------------------------------- must reject --

REJECTED = [
    # Writes, in every form.
    ("drop", "DROP TABLE plant.energy_readings"),
    ("delete", "DELETE FROM plant.energy_readings"),
    ("update", "UPDATE plant.production_lines SET name_fr = 'x'"),
    ("insert", "INSERT INTO plant.shifts VALUES ('X','x','x',0,1)"),
    ("truncate", "TRUNCATE plant.energy_readings"),
    ("create", "CREATE TABLE plant.evil (id int)"),
    ("alter", "ALTER TABLE plant.shifts ADD COLUMN x int"),
    ("grant", "GRANT SELECT ON plant.shifts TO assistant_ro"),
    # Stacked statements and comment tricks.
    ("two statements", "SELECT 1 FROM plant.shifts; DROP TABLE plant.shifts"),
    ("trailing write", "SELECT * FROM plant.shifts; DELETE FROM plant.shifts"),
    ("comment then write", "SELECT 1 FROM plant.shifts; -- ok\nDROP TABLE plant.shifts"),
    # Schemas the agent must not read.
    ("rag schema", "SELECT * FROM rag.chunks"),
    ("app schema", "SELECT * FROM app.feedback"),
    ("pg_catalog", "SELECT * FROM pg_catalog.pg_tables"),
    ("information_schema", "SELECT * FROM information_schema.columns"),
    ("join into rag", "SELECT * FROM plant.shifts s JOIN rag.chunks c ON true"),
    ("subquery into app", "SELECT (SELECT count(*) FROM app.feedback) FROM plant.shifts"),
    # Dangerous functions.
    ("pg_sleep", "SELECT pg_sleep(10) FROM plant.shifts"),
    ("pg_read_file", "SELECT pg_read_file('/etc/passwd') FROM plant.shifts"),
    ("pg_ls_dir", "SELECT pg_ls_dir('/') FROM plant.shifts"),
    ("lo_import", "SELECT lo_import('/etc/passwd') FROM plant.shifts"),
    ("dblink", "SELECT dblink('host=evil', 'SELECT 1') FROM plant.shifts"),
    ("pg_terminate_backend", "SELECT pg_terminate_backend(1) FROM plant.shifts"),
    ("current_setting", "SELECT current_setting('is_superuser') FROM plant.shifts"),
    # Statement shapes that write or lock.
    ("select into", "SELECT * INTO plant.copy FROM plant.shifts"),
    ("for update", "SELECT * FROM plant.shifts FOR UPDATE"),
    ("data-modifying CTE", "WITH d AS (DELETE FROM plant.shifts RETURNING *) SELECT * FROM d"),
    (
        "insert CTE",
        "WITH i AS (INSERT INTO plant.shifts VALUES ('X','x','x',0,1) RETURNING *) SELECT * FROM i",
    ),
    # Malformed or empty.
    ("empty", ""),
    ("whitespace", "   \n  "),
    ("unqualified table", "SELECT * FROM energy_readings"),
    ("no table at all", "SELECT 1"),
]


@pytest.mark.parametrize(("label", "sql"), REJECTED, ids=[label for label, _ in REJECTED])
def test_rejected(label, sql):
    with pytest.raises(SQLGuardError):
        guard_sql(sql)


def test_rejection_messages_are_useful_for_self_correction():
    """The message is fed back to the model, so it must say what was wrong."""
    with pytest.raises(SQLGuardError, match="schema 'rag' is not readable"):
        guard_sql("SELECT * FROM rag.chunks")
    with pytest.raises(SQLGuardError, match="pg_sleep"):
        guard_sql("SELECT pg_sleep(1) FROM plant.shifts")
    with pytest.raises(SQLGuardError, match="exactly one statement"):
        guard_sql("SELECT 1 FROM plant.shifts; SELECT 2 FROM plant.shifts")


def test_case_and_whitespace_do_not_evade():
    """A text blocklist would miss these; an AST does not."""
    for sql in (
        "select PG_SLEEP(10) from plant.shifts",
        "SELECT\n  pg_sleep\n  (10)\nFROM plant.shifts",
        "SELECT/**/pg_sleep(10)FROM plant.shifts",
        "SeLeCt * FrOm RAG.chunks",
    ):
        with pytest.raises(SQLGuardError):
            guard_sql(sql)


# --------------------------------------------------------------- must accept --

ACCEPTED = [
    ("simple select", "SELECT * FROM plant.energy_readings"),
    ("filter", "SELECT usage_kwh FROM plant.energy_readings WHERE load_type = 'Maximum_Load'"),
    (
        "join",
        "SELECT p.plate_id, l.name_fr FROM plant.plate_inspections p "
        "JOIN plant.production_lines l ON l.line_id = p.line_id",
    ),
    (
        "three-way join",
        "SELECT * FROM plant.plate_inspections p "
        "JOIN plant.production_lines l ON l.line_id = p.line_id "
        "JOIN plant.fault_types f ON f.fault_code = p.fault_code",
    ),
    (
        "cte",
        "WITH monthly AS (SELECT date_trunc('month', ts) AS m, sum(usage_kwh) AS kwh "
        "FROM plant.energy_readings GROUP BY 1) SELECT * FROM monthly ORDER BY kwh DESC",
    ),
    (
        "two ctes referencing each other",
        "WITH a AS (SELECT line_id FROM plant.production_lines), "
        "b AS (SELECT line_id FROM a) SELECT * FROM b",
    ),
    (
        "window function",
        "SELECT ts, usage_kwh, avg(usage_kwh) OVER (ORDER BY ts ROWS 3 PRECEDING) "
        "FROM plant.energy_readings",
    ),
    (
        "group by with having",
        "SELECT line_id, count(*) FROM plant.plate_inspections "
        "GROUP BY line_id HAVING count(*) > 100",
    ),
    (
        "union",
        "SELECT line_id FROM plant.production_lines UNION "
        "SELECT line_id FROM plant.maintenance_events",
    ),
    (
        "subquery in where",
        "SELECT * FROM plant.plate_inspections WHERE fault_code IN "
        "(SELECT fault_code FROM plant.fault_types WHERE severity = 3)",
    ),
    (
        "case expression",
        "SELECT CASE WHEN severity = 3 THEN 'high' ELSE 'low' END FROM plant.fault_types",
    ),
    (
        "date functions",
        "SELECT date_trunc('month', ts), extract(hour FROM ts) FROM plant.energy_readings",
    ),
]


@pytest.mark.parametrize(("label", "sql"), ACCEPTED, ids=[label for label, _ in ACCEPTED])
def test_accepted(label, sql):
    result = guard_sql(sql)
    assert result.sql


# ----------------------------------------------------------- limit injection --


def test_limit_is_injected_when_missing():
    result = guard_sql("SELECT * FROM plant.energy_readings")
    assert result.limit_added is True
    assert "LIMIT 200" in result.sql.upper()


def test_existing_limit_is_respected():
    result = guard_sql("SELECT * FROM plant.energy_readings LIMIT 5")
    assert result.limit_added is False
    assert "LIMIT 5" in result.sql.upper()
    assert "LIMIT 200" not in result.sql.upper()


def test_bare_aggregate_needs_no_limit():
    """SELECT count(*) returns one row; a LIMIT would be noise."""
    result = guard_sql("SELECT count(*) FROM plant.energy_readings")
    assert result.is_aggregate is True
    assert result.limit_added is False
    assert "LIMIT" not in result.sql.upper()


def test_multiple_aggregates_still_count_as_aggregate():
    result = guard_sql("SELECT sum(usage_kwh), avg(usage_kwh) FROM plant.energy_readings")
    assert result.is_aggregate is True
    assert result.limit_added is False


def test_group_by_is_not_a_bare_aggregate():
    """GROUP BY can return many rows, so it still needs a LIMIT."""
    result = guard_sql("SELECT line_id, count(*) FROM plant.plate_inspections GROUP BY line_id")
    assert result.is_aggregate is False
    assert result.limit_added is True


def test_custom_default_limit():
    result = guard_sql("SELECT * FROM plant.shifts", default_limit=7)
    assert "LIMIT 7" in result.sql.upper()


# ------------------------------------------------------------------- tables --


def test_tables_are_reported():
    result = guard_sql(
        "SELECT * FROM plant.plate_inspections p "
        "JOIN plant.production_lines l ON l.line_id = p.line_id"
    )
    assert result.tables == ["plant.plate_inspections", "plant.production_lines"]


def test_cte_names_are_not_reported_as_tables():
    result = guard_sql(
        "WITH monthly AS (SELECT ts FROM plant.energy_readings) SELECT * FROM monthly"
    )
    assert result.tables == ["plant.energy_readings"]


def test_allowed_schemas_is_configurable():
    with pytest.raises(SQLGuardError):
        guard_sql("SELECT * FROM other.t", allowed_schemas=("plant",))
    assert guard_sql("SELECT * FROM other.t", allowed_schemas=("other",)).tables == ["other.t"]


def test_guard_output_is_reparseable():
    """Whatever the guard returns must itself pass the guard."""
    for _, sql in ACCEPTED:
        once = guard_sql(sql)
        twice = guard_sql(once.sql)
        assert twice.sql == once.sql


# ------------------------------------------------------------- adversarial --

EVASION_ATTEMPTS = [
    ("quoted schema", 'SELECT * FROM "rag"."chunks"'),
    ("mixed-case schema", "SELECT * FROM RaG.Chunks"),
    ("catalog-qualified", "SELECT * FROM steel.rag.chunks"),
    ("lateral join", "SELECT * FROM plant.shifts s, LATERAL (SELECT * FROM app.feedback) f"),
    ("pg_sleep in subquery", "SELECT * FROM plant.shifts WHERE 1 = (SELECT pg_sleep(9))"),
    ("function in ORDER BY", "SELECT * FROM plant.shifts ORDER BY pg_sleep(5)"),
    ("set-returning function in FROM", "SELECT * FROM plant.shifts, pg_ls_dir('/')"),
    (
        "union reaching rag",
        "SELECT shift_code FROM plant.shifts UNION SELECT source_id FROM rag.chunks",
    ),
    ("EXPLAIN wrapper", "EXPLAIN SELECT * FROM plant.shifts"),
    ("COPY", "COPY plant.shifts TO '/tmp/x'"),
    (
        "delete nested two CTEs deep",
        "WITH a AS (WITH b AS (DELETE FROM plant.shifts RETURNING *) SELECT * FROM b) "
        "SELECT * FROM a",
    ),
    ("FOR SHARE", "SELECT * FROM plant.shifts FOR SHARE"),
]


@pytest.mark.parametrize(
    ("label", "sql"), EVASION_ATTEMPTS, ids=[label for label, _ in EVASION_ATTEMPTS]
)
def test_evasion_attempts_are_rejected(label, sql):
    with pytest.raises(SQLGuardError):
        guard_sql(sql)


def test_cte_may_shadow_a_forbidden_table_name():
    """Naming a CTE `chunks` is fine; it is the schema that matters.

    The CTE never touches rag.chunks, so rejecting this would be a false
    positive that blocks a legitimate query.
    """
    result = guard_sql("WITH chunks AS (SELECT 1 AS x FROM plant.shifts) SELECT * FROM chunks")
    assert result.tables == ["plant.shifts"]
