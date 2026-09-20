"""Schema context rendering.

Two regressions are pinned here, both of which were silent: a prompt missing
its foreign keys, and a wide table crowding out everything else.
"""

from steel_assistant.tools.schema_context import (
    ColumnInfo,
    TableInfo,
    render_schema_context,
)

# Real comments in this project are bilingual and about this long, which is
# why they dominate a wide table.
REALISTIC_COMMENT = (
    "Coordonnee X minimale du defaut en pixels / Minimum X coordinate of the fault in pixels"
)


def _column(name: str, comment: str | None = REALISTIC_COMMENT) -> ColumnInfo:
    return ColumnInfo(name=name, data_type="integer", nullable=True, comment=comment)


def _wide_table() -> TableInfo:
    return TableInfo(
        schema="plant",
        name="plate_inspections",
        comment="Inspections",
        columns=[
            _column("plate_id"),
            _column("line_id"),
            _column("fault_code"),
            *[_column(f"measure_{i}") for i in range(25)],
        ],
        primary_key=["plate_id"],
        foreign_keys=[
            ("line_id", "plant.production_lines", "line_id"),
            ("fault_code", "plant.fault_types", "fault_code"),
        ],
        sample_rows=[(1, "L1", "Bumps")],
    )


def test_foreign_keys_are_rendered():
    """Without these the model is told nothing about how tables join."""
    rendered = render_schema_context([_wide_table()])
    assert "FOREIGN KEY line_id -> plant.production_lines.line_id" in rendered
    assert "FOREIGN KEY fault_code -> plant.fault_types.fault_code" in rendered


def test_every_column_is_listed_even_in_a_wide_table():
    rendered = render_schema_context([_wide_table()])
    for index in range(25):
        assert f"measure_{index} integer" in rendered


def test_trailing_columns_lose_their_comments():
    rendered = render_schema_context([_wide_table()], commented_columns=5)
    lines = rendered.splitlines()
    measure_24 = next(i for i, line in enumerate(lines) if "measure_24 integer" in line)
    # The line after a commented column is its comment; here there must be none.
    following = lines[measure_24 + 1] if measure_24 + 1 < len(lines) else ""
    assert not following.strip().startswith("--")


def test_keys_keep_their_comments_wherever_they_sit():
    """A key's comment survives even past the comment budget, because joins
    depend on it."""
    table = _wide_table()
    table.columns.append(_column("late_fk", "the important one"))
    table.foreign_keys.append(("late_fk", "plant.shifts", "shift_code"))
    rendered = render_schema_context([table], commented_columns=1)
    assert "the important one" in rendered


def test_primary_key_and_not_null_are_flagged():
    table = TableInfo(
        schema="plant",
        name="t",
        comment=None,
        columns=[ColumnInfo("id", "integer", False, None)],
        primary_key=["id"],
        foreign_keys=[],
        sample_rows=[],
    )
    rendered = render_schema_context([table])
    assert "[PK, NOT NULL]" in rendered


def test_sample_rows_are_truncated():
    table = TableInfo(
        schema="plant",
        name="t",
        comment=None,
        columns=[_column("x")],
        primary_key=[],
        foreign_keys=[],
        sample_rows=[("y" * 500,)],
    )
    rendered = render_schema_context([table], max_sample_chars=20)
    assert "..." in rendered
    assert len(rendered) < 300


def test_wide_table_is_materially_smaller_than_fully_commented():
    """The reason this exists: one table was 40% of the whole prompt."""
    full = render_schema_context([_wide_table()], commented_columns=100)
    trimmed = render_schema_context([_wide_table()], commented_columns=12)
    assert len(trimmed) < len(full) * 0.75
