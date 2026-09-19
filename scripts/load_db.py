#!/usr/bin/env python
"""Load the raw UCI files into schema ``plant``.

Order matters: the small reference tables carry the foreign keys that
``plate_inspections`` depends on, so they are seeded first. The synthetic
enrichment (line assignment, inspection timestamps, maintenance events) is a
separate second pass in ``generate_synthetic_tables.py``.

Idempotent: every table is truncated before it is filled, so re-running gives
the same database.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from steel_assistant.db.engine import superuser_engine  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW = REPO_ROOT / "data" / "raw"

# Three lines spanning the plant: hot rolling, cold rolling, finishing.
PRODUCTION_LINES = [
    ("L1", "Ligne de laminage à chaud", "Hot rolling line", "hot_rolling", 2005),
    ("L2", "Ligne de laminage à froid", "Cold rolling line", "cold_rolling", 2011),
    ("L3", "Ligne de finition et inspection", "Finishing and inspection line", "finishing", 2016),
]

# Standard 3x8 pattern. The night shift wraps past midnight.
SHIFTS = [
    ("M", "Poste du matin", "Morning shift", 6, 14),
    ("A", "Poste d'après-midi", "Afternoon shift", 14, 22),
    ("N", "Poste de nuit", "Night shift", 22, 6),
]

# fault_code, label_fr, label_en, severity, procedure_doc_id
# Codes are exactly the seven one-hot columns of UCI id=198. Severity drives the
# quality-hold rules in the legacy code corpus, so it must stay stable.
FAULT_TYPES = [
    ("Pastry", "Feuilletage", "Pastry", 2, "PROC-FLT-PAST"),
    ("Z_Scratch", "Rayure en Z", "Z-shaped scratch", 3, "PROC-FLT-ZSCR"),
    ("K_Scratch", "Rayure en K", "K-shaped scratch", 3, "PROC-FLT-KSCR"),
    ("Stains", "Taches", "Stains", 1, "PROC-FLT-STAI"),
    ("Dirtiness", "Souillures", "Dirtiness", 1, "PROC-FLT-DIRT"),
    ("Bumps", "Bosses", "Bumps", 2, "PROC-FLT-BUMP"),
    ("Other_Faults", "Autres défauts", "Other faults", 2, "PROC-FLT-OTHR"),
]

FAULT_CODES = [row[0] for row in FAULT_TYPES]

ENERGY_COLUMNS = {
    "date": "ts",
    "Usage_kWh": "usage_kwh",
    "Lagging_Current_Reactive.Power_kVarh": "lagging_current_reactive_power_kvarh",
    "Leading_Current_Reactive_Power_kVarh": "leading_current_reactive_power_kvarh",
    "CO2(tCO2)": "co2_tco2",
    "Lagging_Current_Power_Factor": "lagging_current_power_factor",
    "Leading_Current_Power_Factor": "leading_current_power_factor",
    "NSM": "nsm",
    "WeekStatus": "week_status",
    "Day_of_week": "day_of_week",
    "Load_Type": "load_type",
}

PLATE_COLUMNS = {
    "X_Minimum": "x_minimum",
    "X_Maximum": "x_maximum",
    "Y_Minimum": "y_minimum",
    "Y_Maximum": "y_maximum",
    "Pixels_Areas": "pixels_areas",
    "X_Perimeter": "x_perimeter",
    "Y_Perimeter": "y_perimeter",
    "Sum_of_Luminosity": "sum_of_luminosity",
    "Minimum_of_Luminosity": "minimum_of_luminosity",
    "Maximum_of_Luminosity": "maximum_of_luminosity",
    "Length_of_Conveyer": "length_of_conveyer",
    "Steel_Plate_Thickness": "steel_plate_thickness",
    "Edges_Index": "edges_index",
    "Empty_Index": "empty_index",
    "Square_Index": "square_index",
    "Outside_X_Index": "outside_x_index",
    "Edges_X_Index": "edges_x_index",
    "Edges_Y_Index": "edges_y_index",
    "Outside_Global_Index": "outside_global_index",
    "LogOfAreas": "log_of_areas",
    "Log_X_Index": "log_x_index",
    "Log_Y_Index": "log_y_index",
    "Orientation_Index": "orientation_index",
    "Luminosity_Index": "luminosity_index",
    "SigmoidOfAreas": "sigmoid_of_areas",
}


def seed_reference_tables() -> None:
    """Fill production_lines, shifts and fault_types."""
    engine = superuser_engine()
    with engine.begin() as conn:
        # plate_inspections and maintenance_events point here, so clear them too.
        conn.execute(
            text(
                "TRUNCATE plant.production_lines, plant.shifts, plant.fault_types, "
                "plant.plate_inspections, plant.maintenance_events CASCADE"
            )
        )
        conn.execute(
            text(
                "INSERT INTO plant.production_lines "
                "(line_id, name_fr, name_en, process, commissioned_year) "
                "VALUES (:line_id, :name_fr, :name_en, :process, :year)"
            ),
            [
                {"line_id": a, "name_fr": b, "name_en": c, "process": d, "year": e}
                for a, b, c, d, e in PRODUCTION_LINES
            ],
        )
        conn.execute(
            text(
                "INSERT INTO plant.shifts (shift_code, label_fr, label_en, start_hour, end_hour) "
                "VALUES (:code, :fr, :en, :start, :end)"
            ),
            [{"code": a, "fr": b, "en": c, "start": d, "end": e} for a, b, c, d, e in SHIFTS],
        )
        conn.execute(
            text(
                "INSERT INTO plant.fault_types "
                "(fault_code, label_fr, label_en, severity, procedure_doc_id) "
                "VALUES (:code, :fr, :en, :sev, :doc)"
            ),
            [{"code": a, "fr": b, "en": c, "sev": d, "doc": e} for a, b, c, d, e in FAULT_TYPES],
        )
    print(
        f"  production_lines {len(PRODUCTION_LINES)}  "
        f"shifts {len(SHIFTS)}  fault_types {len(FAULT_TYPES)}"
    )


def load_energy() -> int:
    """Load plant.energy_readings from the UCI energy CSV."""
    frame = pd.read_csv(RAW / "energy_851.csv", encoding="utf-8-sig")
    missing = set(ENERGY_COLUMNS) - set(frame.columns)
    if missing:
        raise RuntimeError(f"energy CSV is missing expected columns: {sorted(missing)}")

    frame = frame[list(ENERGY_COLUMNS)].rename(columns=ENERGY_COLUMNS)
    # Day-first, and the label marks the END of each interval. Explicit format:
    # inference would silently read 03/01 as 3 January in some rows and 1 March
    # in others. See DECISIONS.md.
    frame["ts"] = pd.to_datetime(frame["ts"], format="%d/%m/%Y %H:%M")
    frame = frame.sort_values("ts").reset_index(drop=True)

    if frame["ts"].duplicated().any():
        raise RuntimeError("duplicate timestamps in the energy data; ts is the primary key")

    engine = superuser_engine()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE plant.energy_readings"))
    frame.to_sql(
        "energy_readings",
        engine,
        schema="plant",
        if_exists="append",
        index=False,
        chunksize=5_000,
        method="multi",
    )
    return len(frame)


def load_plates() -> int:
    """Load plant.plate_inspections, collapsing both sets of one-hot columns."""
    frame = pd.read_csv(RAW / "plates_198.csv", encoding="utf-8-sig")

    missing = set(PLATE_COLUMNS) - set(frame.columns)
    if missing:
        raise RuntimeError(f"plates CSV is missing expected columns: {sorted(missing)}")
    missing_faults = set(FAULT_CODES) - set(frame.columns)
    if missing_faults:
        raise RuntimeError(f"plates CSV is missing fault columns: {sorted(missing_faults)}")

    # Exactly one fault and exactly one grade per plate. Verified at sanity-check
    # time for all 1941 rows; assert it rather than assume it.
    fault_sums = frame[FAULT_CODES].sum(axis=1)
    if not (fault_sums == 1).all():
        bad = int((fault_sums != 1).sum())
        raise RuntimeError(f"{bad} plates do not have exactly one fault; cannot collapse")
    grade_sums = frame[["TypeOfSteel_A300", "TypeOfSteel_A400"]].sum(axis=1)
    if not (grade_sums == 1).all():
        bad = int((grade_sums != 1).sum())
        raise RuntimeError(f"{bad} plates do not have exactly one steel grade")

    out = frame[list(PLATE_COLUMNS)].rename(columns=PLATE_COLUMNS).copy()
    out.insert(0, "plate_id", range(1, len(frame) + 1))
    out["fault_code"] = frame[FAULT_CODES].idxmax(axis=1)
    out["steel_grade"] = frame["TypeOfSteel_A300"].map({1: "A300", 0: "A400"})
    # line_id and inspected_at are filled by generate_synthetic_tables.py.

    engine = superuser_engine()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE plant.plate_inspections CASCADE"))
    out.to_sql(
        "plate_inspections",
        engine,
        schema="plant",
        if_exists="append",
        index=False,
        chunksize=1_000,
        method="multi",
    )
    return len(out)


def report_counts() -> None:
    """Print the row count of every table in schema plant."""
    engine = superuser_engine()
    with engine.connect() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'plant' ORDER BY tablename"
                )
            )
            .scalars()
            .all()
        )
        print("\nRow counts in schema plant:")
        for table in tables:
            count = conn.execute(text(f"SELECT count(*) FROM plant.{table}")).scalar_one()
            print(f"  {table:<20} {count:>7,}")


def main() -> int:
    """Seed reference tables, then load both real datasets."""
    print("Reference tables")
    seed_reference_tables()

    print("\nplant.energy_readings")
    energy_rows = load_energy()
    print(f"  loaded {energy_rows:,} rows")

    print("\nplant.plate_inspections")
    plate_rows = load_plates()
    print(f"  loaded {plate_rows:,} rows")

    report_counts()
    print("\nNext: scripts/generate_synthetic_tables.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
