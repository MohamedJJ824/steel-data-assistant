"""Plan section 6.5: assistant_ro must be incapable of writing or of reading rag/app.

These are the tests that make the read-only claim in the README true. They run
against a live database and are skipped when one is not reachable.
"""

import os

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def ro_conn():
    from steel_assistant.db.engine import assistant_engine

    if not os.environ.get("ASSISTANT_RO_PASSWORD"):
        pytest.skip("ASSISTANT_RO_PASSWORD not set")
    try:
        engine = assistant_engine()
        with engine.connect() as conn:
            yield conn
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable: {exc}")


def test_can_select_from_plant(ro_conn):
    count = ro_conn.execute(text("SELECT count(*) FROM plant.energy_readings")).scalar_one()
    assert count == 35_040


def test_statement_timeout_is_five_seconds(ro_conn):
    assert ro_conn.execute(text("SHOW statement_timeout")).scalar_one() == "5s"


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO plant.fault_types VALUES ('X','x','x',1,NULL)",
        "UPDATE plant.production_lines SET name_fr = 'x'",
        "DELETE FROM plant.energy_readings",
        "CREATE TABLE plant.evil (id int)",
        "DROP TABLE plant.shifts",
    ],
)
def test_writes_are_rejected(ro_conn, statement):
    with pytest.raises(Exception):  # noqa: B017, PT011
        ro_conn.execute(text(statement))
    ro_conn.rollback()


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT count(*) FROM rag.chunks",
        "SELECT count(*) FROM app.feedback",
        "SELECT count(*) FROM app.request_log",
    ],
)
def test_other_schemas_are_invisible(ro_conn, statement):
    with pytest.raises(Exception):  # noqa: B017, PT011
        ro_conn.execute(text(statement))
    ro_conn.rollback()


def test_writes_still_rejected_when_read_only_is_disabled():
    """Defence in depth: prove the GRANTS alone stop writes.

    The app's own engine sets ``postgresql_readonly``, which would mask this.
    So connect deliberately without it and with the role's session flag turned
    off, leaving nothing but the grants. If this passes, the read-only promise
    does not rest on any single setting a compromised session could flip.
    """
    from sqlalchemy import create_engine

    from steel_assistant.config import get_settings
    from steel_assistant.db.engine import _password, _url

    settings = get_settings()
    engine = create_engine(_url(settings.db.assistant_user, _password("ASSISTANT_RO_PASSWORD")))
    try:
        with engine.connect() as conn:
            conn.execute(text("SET SESSION default_transaction_read_only = off"))
            conn.commit()
            assert conn.execute(text("SHOW default_transaction_read_only")).scalar_one() == "off"

            for statement in (
                "DELETE FROM plant.energy_readings",
                "UPDATE plant.production_lines SET name_fr = 'x'",
                "INSERT INTO plant.shifts VALUES ('X','x','x',0,1)",
                "CREATE TABLE plant.evil (id int)",
            ):
                with pytest.raises(Exception) as excinfo:  # noqa: PT011
                    conn.execute(text(statement))
                assert "permission denied" in str(excinfo.value).lower(), statement
                conn.rollback()
    finally:
        engine.dispose()
