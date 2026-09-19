"""Day 1 acceptance criteria, as tests."""

import os

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def conn():
    from steel_assistant.db.engine import superuser_engine

    if not os.environ.get("POSTGRES_PASSWORD"):
        pytest.skip("POSTGRES_PASSWORD not set")
    try:
        with superuser_engine().connect() as connection:
            yield connection
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable: {exc}")


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        ("energy_readings", 35_040),
        ("plate_inspections", 1_941),
        ("production_lines", 3),
        ("shifts", 3),
        ("fault_types", 7),
        ("maintenance_events", 300),
    ],
)
def test_row_counts(conn, table, expected):
    assert conn.execute(text(f"SELECT count(*) FROM plant.{table}")).scalar_one() == expected


def test_energy_spans_exactly_2018(conn):
    first, last = conn.execute(text("SELECT min(ts), max(ts) FROM plant.energy_readings")).one()
    assert str(first) == "2018-01-01 00:00:00"
    assert str(last) == "2018-12-31 23:45:00"


def test_every_plate_has_a_line_and_a_timestamp(conn):
    orphans = conn.execute(
        text(
            "SELECT count(*) FROM plant.plate_inspections "
            "WHERE line_id IS NULL OR inspected_at IS NULL"
        )
    ).scalar_one()
    assert orphans == 0


def test_all_columns_are_documented(conn):
    """The text-to-SQL tool builds its schema context from these comments, so a
    missing one degrades generation quality silently."""
    undocumented = (
        conn.execute(
            text(
                """
            SELECT c.table_name || '.' || c.column_name
            FROM information_schema.columns c
            JOIN pg_class pc ON pc.relname = c.table_name
            JOIN pg_namespace pn ON pn.oid = pc.relnamespace AND pn.nspname = 'plant'
            WHERE c.table_schema = 'plant'
              AND col_description(pc.oid, c.ordinal_position) IS NULL
            ORDER BY 1
            """
            )
        )
        .scalars()
        .all()
    )
    assert undocumented == []


def test_maintenance_downtime_matches_the_timestamps(conn):
    mismatches = conn.execute(
        text(
            "SELECT count(*) FROM plant.maintenance_events "
            "WHERE downtime_minutes <> EXTRACT(EPOCH FROM (ended_at - started_at)) / 60"
        )
    ).scalar_one()
    assert mismatches == 0


def test_preventive_events_have_no_fault(conn):
    bad = conn.execute(
        text(
            "SELECT count(*) FROM plant.maintenance_events "
            "WHERE category = 'preventive' AND fault_code IS NOT NULL"
        )
    ).scalar_one()
    assert bad == 0
