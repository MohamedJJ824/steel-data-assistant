#!/usr/bin/env python
"""Add the synthetic layer that links the two unrelated public datasets.

UCI 851 (energy) and UCI 198 (plate faults) share no key. Without a thin
connecting layer there are no cross-table questions to ask, and cross-table
questions are the point of the text-to-SQL tool. So this script invents, from a
fixed seed:

* which line inspected each plate, and when;
* a year of maintenance events with downtime, category and fault attribution.

Everything written here is fabricated and is listed as such in
``docs/DATA_CARD.md``. Nothing in the real UCI measurements is modified.

Deterministic: seed 42, so two runs produce byte-identical tables.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from steel_assistant.config import get_settings  # noqa: E402
from steel_assistant.db.engine import superuser_engine  # noqa: E402

YEAR_START = datetime(2018, 1, 1)
YEAR_END = datetime(2019, 1, 1)
YEAR_MINUTES = int((YEAR_END - YEAR_START).total_seconds() // 60)

LINES = ["L1", "L2", "L3"]

# Per-fault line weights. Deliberately uneven so that "which line has the most
# Bumps" has one defensible answer rather than three near-ties. The shape is
# plausible: hot rolling bruises plates, cold rolling scratches them, finishing
# is where surface contamination shows up.
FAULT_LINE_WEIGHTS: dict[str, tuple[float, float, float]] = {
    "Bumps": (0.62, 0.23, 0.15),
    "Pastry": (0.55, 0.28, 0.17),
    "Z_Scratch": (0.18, 0.64, 0.18),
    "K_Scratch": (0.15, 0.67, 0.18),
    "Stains": (0.16, 0.24, 0.60),
    "Dirtiness": (0.14, 0.22, 0.64),
    "Other_Faults": (0.34, 0.33, 0.33),
}

# Hour-of-day weights for inspections: day shifts inspect more than nights.
HOUR_WEIGHTS = np.array(
    [0.4] * 6  # 00-05 night, quiet
    + [1.6] * 8  # 06-13 morning shift
    + [1.4] * 8  # 14-21 afternoon shift
    + [0.5] * 2  # 22-23 night shift starting
)

N_EVENTS = 300
FIRST_EVENT_ID = 1001
# Maintenance reports exist for only some events; the rest were never written up.
# That gap is intentional: it gives the agent a reason to say "no report exists".
N_REPORTS = 20

# Mean corrective downtime in minutes by fault severity. Severity 3 dominates
# total downtime, which makes "which fault cost the most minutes" answerable.
DOWNTIME_MEAN_BY_SEVERITY = {1: 35.0, 2: 70.0, 3: 165.0}
PREVENTIVE_DOWNTIME_MEAN = 45.0


def _random_2018_timestamps(rng: np.random.Generator, n: int) -> np.ndarray:
    """Draw n timestamps in 2018, biased towards day-shift hours."""
    days = rng.integers(0, 365, size=n)
    hours = rng.choice(24, size=n, p=HOUR_WEIGHTS / HOUR_WEIGHTS.sum())
    minutes = rng.integers(0, 60, size=n)
    return np.array(
        [
            YEAR_START + timedelta(days=int(d), hours=int(h), minutes=int(m))
            for d, h, m in zip(days, hours, minutes, strict=True)
        ]
    )


def enrich_plate_inspections(rng: np.random.Generator) -> int:
    """Give every plate a production line and an inspection timestamp."""
    engine = superuser_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT plate_id, fault_code FROM plant.plate_inspections ORDER BY plate_id")
        ).all()
    if not rows:
        raise RuntimeError("plant.plate_inspections is empty; run scripts/load_db.py first")

    timestamps = _random_2018_timestamps(rng, len(rows))
    updates = []
    for (plate_id, fault_code), ts in zip(rows, timestamps, strict=True):
        weights = FAULT_LINE_WEIGHTS.get(fault_code, (1 / 3, 1 / 3, 1 / 3))
        line_id = str(rng.choice(LINES, p=np.array(weights) / sum(weights)))
        updates.append({"plate_id": plate_id, "line_id": line_id, "ts": ts.isoformat()})

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE plant.plate_inspections "
                "SET line_id = :line_id, inspected_at = CAST(:ts AS timestamp) "
                "WHERE plate_id = :plate_id"
            ),
            updates,
        )
    return len(updates)


def generate_maintenance_events(rng: np.random.Generator) -> int:
    """Build a year of maintenance events tied to lines and fault types."""
    engine = superuser_engine()
    with engine.connect() as conn:
        severity_by_fault = dict(
            conn.execute(text("SELECT fault_code, severity FROM plant.fault_types")).all()
        )

    fault_codes = sorted(severity_by_fault)
    # Corrective work follows the faults that actually occur, so weight the draw
    # by how common each fault is in the inspection data.
    with engine.connect() as conn:
        observed = dict(
            conn.execute(
                text("SELECT fault_code, count(*) FROM plant.plate_inspections GROUP BY fault_code")
            ).all()
        )
    fault_p = np.array([observed.get(code, 1) for code in fault_codes], dtype=float)
    fault_p /= fault_p.sum()

    starts = sorted(_random_2018_timestamps(rng, N_EVENTS))
    categories = rng.choice(["preventive", "corrective"], size=N_EVENTS, p=[0.4, 0.6])

    events = []
    for offset, (start, category) in enumerate(zip(starts, categories, strict=True)):
        event_id = FIRST_EVENT_ID + offset
        if category == "corrective":
            fault_code = str(rng.choice(fault_codes, p=fault_p))
            mean = DOWNTIME_MEAN_BY_SEVERITY[severity_by_fault[fault_code]]
        else:
            fault_code = None
            mean = PREVENTIVE_DOWNTIME_MEAN
        # Lognormal: most interventions are short, a few run long. Clamped so a
        # single freak draw cannot dominate the yearly totals.
        downtime = int(np.clip(rng.lognormal(np.log(mean), 0.55), 10, 600))
        events.append(
            {
                "event_id": event_id,
                "line_id": str(rng.choice(LINES)),
                "started_at": start.isoformat(),
                "ended_at": (start + timedelta(minutes=downtime)).isoformat(),
                "downtime_minutes": downtime,
                "category": str(category),
                "fault_code": fault_code,
                "report_doc_id": None,
            }
        )

    # Attach reports to the longest corrective events: those are the ones a real
    # plant writes up, and it keeps the linked documents worth asking about.
    corrective = [e for e in events if e["category"] == "corrective"]
    corrective.sort(key=lambda e: e["downtime_minutes"], reverse=True)
    for event in corrective[:N_REPORTS]:
        event["report_doc_id"] = f"MNT-RPT-{event['event_id']}"

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE plant.maintenance_events"))
        conn.execute(
            text(
                "INSERT INTO plant.maintenance_events "
                "(event_id, line_id, started_at, ended_at, downtime_minutes, "
                " category, fault_code, report_doc_id) "
                "VALUES (:event_id, :line_id, CAST(:started_at AS timestamp), "
                " CAST(:ended_at AS timestamp), :downtime_minutes, :category, "
                " :fault_code, :report_doc_id)"
            ),
            events,
        )
    return len(events)


def summarise() -> None:
    """Print the facts the document corpus will have to stay consistent with."""
    engine = superuser_engine()
    with engine.connect() as conn:
        print("\nPlates per line:")
        for line_id, count in conn.execute(
            text(
                "SELECT line_id, count(*) FROM plant.plate_inspections "
                "GROUP BY line_id ORDER BY line_id"
            )
        ):
            print(f"  {line_id}  {count:>5,}")

        print("\nDowntime by fault (corrective only, minutes):")
        for code, events, minutes in conn.execute(
            text(
                "SELECT fault_code, count(*), sum(downtime_minutes) "
                "FROM plant.maintenance_events WHERE fault_code IS NOT NULL "
                "GROUP BY fault_code ORDER BY sum(downtime_minutes) DESC"
            )
        ):
            print(f"  {code:<14} {events:>4} events  {minutes:>7,} min")

        threshold = conn.execute(
            text(
                "SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY usage_kwh) "
                "FROM plant.energy_readings"
            )
        ).scalar_one()
        print(f"\nPeak-load alert threshold (p95 of usage_kwh): {threshold:.2f} kWh")

        reports = conn.execute(
            text("SELECT count(*) FROM plant.maintenance_events WHERE report_doc_id IS NOT NULL")
        ).scalar_one()
        print(f"Maintenance events with a report document: {reports}")


def main() -> int:
    """Generate the synthetic layer with the configured global seed."""
    seed = get_settings().seed
    rng = np.random.default_rng(seed)
    print(f"Synthetic generation, seed={seed}")

    updated = enrich_plate_inspections(rng)
    print(f"  plate_inspections enriched: {updated:,} rows given a line and a timestamp")

    events = generate_maintenance_events(rng)
    print(f"  maintenance_events generated: {events:,} rows")

    summarise()
    print("\nEvery column written here is listed in docs/DATA_CARD.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
