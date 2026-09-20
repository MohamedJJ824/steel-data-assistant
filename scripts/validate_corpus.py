#!/usr/bin/env python
"""Check that the document corpus and the database agree.

The documents are generated from database facts, so they start consistent. This
script is what catches them drifting apart afterwards — a regenerated synthetic
layer, a hand-edited document, a renamed fault code.

Checks:
  1. every doc_id is unique and matches its filename
  2. every front-matter reference (event_id, fault_code, line_id) exists in the DB
  3. every fault_types.procedure_doc_id has a file
  4. every maintenance_events.report_doc_id has a file, and vice versa
  5. maintenance reports state the downtime their event actually has
  6. required front-matter fields are present
  7. the peak-load policy states the threshold the data actually gives

Exit code is non-zero if any check fails, so `make seed` stops on a problem.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import frontmatter
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from steel_assistant.db.engine import superuser_engine  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "corpus" / "docs"

REQUIRED_FIELDS = ("doc_id", "title", "doc_type", "version", "date")
VALID_DOC_TYPES = {"procedure", "manual", "maintenance_report", "policy", "reference"}


class Report:
    """Collects failures so that one run reports every problem, not just the first."""

    def __init__(self) -> None:
        """Start with no failures."""
        self.errors: list[str] = []
        self.checks = 0

    def check(self, condition: bool, message: str) -> None:
        """Record one assertion."""
        self.checks += 1
        if not condition:
            self.errors.append(message)

    def section(self, name: str) -> None:
        """Print a progress heading."""
        print(f"\n{name}")

    def ok(self, message: str) -> None:
        """Print a passing line."""
        print(f"  ok   {message}")


def load_documents() -> list[tuple[Path, frontmatter.Post]]:
    """Parse every markdown file in the corpus."""
    return [
        (path, frontmatter.loads(path.read_text(encoding="utf-8")))
        for path in sorted(DOCS_DIR.glob("*.md"))
    ]


def main() -> int:  # noqa: PLR0912, PLR0915 - a linear list of checks reads better flat
    """Run every consistency check."""
    if not DOCS_DIR.is_dir() or not any(DOCS_DIR.glob("*.md")):
        print("No documents found. Run scripts/generate_docs.py first.", file=sys.stderr)
        return 1

    documents = load_documents()
    report = Report()
    print(f"Validating {len(documents)} documents against the database")

    engine = superuser_engine()
    with engine.connect() as conn:
        db_fault_codes = set(
            conn.execute(text("SELECT fault_code FROM plant.fault_types")).scalars()
        )
        db_line_ids = set(
            conn.execute(text("SELECT line_id FROM plant.production_lines")).scalars()
        )
        db_event_ids = set(
            conn.execute(text("SELECT event_id FROM plant.maintenance_events")).scalars()
        )
        procedure_docs = {
            code: doc
            for code, doc in conn.execute(
                text(
                    "SELECT fault_code, procedure_doc_id FROM plant.fault_types "
                    "WHERE procedure_doc_id IS NOT NULL"
                )
            )
        }
        report_docs = {
            doc: (event_id, downtime)
            for doc, event_id, downtime in conn.execute(
                text(
                    "SELECT report_doc_id, event_id, downtime_minutes "
                    "FROM plant.maintenance_events WHERE report_doc_id IS NOT NULL"
                )
            )
        }
        threshold = float(
            conn.execute(
                text(
                    "SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY usage_kwh) "
                    "FROM plant.energy_readings"
                )
            ).scalar_one()
        )

    by_doc_id: dict[str, Path] = {}

    # 1 + 6: identity and required fields.
    report.section("Front matter")
    for path, post in documents:
        meta = post.metadata
        doc_id = meta.get("doc_id")
        for field in REQUIRED_FIELDS:
            report.check(field in meta, f"{path.name}: missing front-matter field '{field}'")
        report.check(
            doc_id is not None and path.stem == str(doc_id),
            f"{path.name}: filename does not match doc_id {doc_id!r}",
        )
        report.check(
            meta.get("doc_type") in VALID_DOC_TYPES,
            f"{path.name}: unknown doc_type {meta.get('doc_type')!r}",
        )
        if doc_id is not None:
            report.check(
                str(doc_id) not in by_doc_id,
                f"{path.name}: duplicate doc_id {doc_id!r} (also {by_doc_id.get(str(doc_id))})",
            )
            by_doc_id[str(doc_id)] = path
        report.check(bool(post.content.strip()), f"{path.name}: empty body")
    report.ok(f"{len(by_doc_id)} unique doc_ids, required fields present")

    # 2: references resolve.
    report.section("References resolve against the database")
    for path, post in documents:
        meta = post.metadata
        if (code := meta.get("fault_code")) is not None:
            report.check(
                str(code) in db_fault_codes,
                f"{path.name}: fault_code {code!r} is not in plant.fault_types",
            )
        if (line_id := meta.get("line_id")) is not None:
            report.check(
                str(line_id) in db_line_ids,
                f"{path.name}: line_id {line_id!r} is not in plant.production_lines",
            )
        if (event_id := meta.get("event_id")) is not None:
            report.check(
                int(event_id) in db_event_ids,
                f"{path.name}: event_id {event_id} is not in plant.maintenance_events",
            )
    report.ok("every fault_code, line_id and event_id reference exists")

    # 3: every procedure referenced by the DB has a file.
    report.section("Procedure documents")
    for code, doc_id in sorted(procedure_docs.items()):
        report.check(
            doc_id in by_doc_id,
            f"fault_types.{code}.procedure_doc_id = {doc_id!r} has no file",
        )
    report.ok(f"{len(procedure_docs)} procedures referenced by fault_types all exist")

    # 4: report documents match both ways.
    report.section("Maintenance reports")
    for doc_id, (event_id, _) in sorted(report_docs.items()):
        report.check(
            doc_id in by_doc_id,
            f"maintenance_events.{event_id}.report_doc_id = {doc_id!r} has no file",
        )
    corpus_reports = {
        str(post.metadata["doc_id"])
        for _, post in documents
        if post.metadata.get("doc_type") == "maintenance_report"
    }
    orphans = corpus_reports - set(report_docs)
    report.check(
        not orphans, f"report documents with no matching event: {sorted(orphans)}"
    )
    report.ok(f"{len(report_docs)} reports match their events in both directions")

    # 5: reports state the downtime their event actually has.
    report.section("Reported downtime matches the database")
    for path, post in documents:
        if post.metadata.get("doc_type") != "maintenance_report":
            continue
        doc_id = str(post.metadata["doc_id"])
        if doc_id not in report_docs:
            continue
        _, downtime = report_docs[doc_id]
        report.check(
            re.search(rf"\b{downtime}\b", post.content) is not None,
            f"{path.name}: does not state its downtime of {downtime} minutes",
        )
    report.ok("every report states its event's real downtime")

    # 7: the policy threshold matches the data.
    report.section("Peak-load threshold")
    policy = by_doc_id.get("POL-ENR-PEAK")
    if policy is None:
        report.check(False, "POL-ENR-PEAK is missing")
    else:
        content = policy.read_text(encoding="utf-8")
        rounded = int(round(threshold))
        report.check(
            f"{rounded} kWh" in content,
            f"POL-ENR-PEAK does not state the rounded threshold of {rounded} kWh",
        )
        # The exact value is written French-style, with a comma decimal.
        exact_fr = f"{threshold:.2f}".replace(".", ",")
        report.check(
            exact_fr in content,
            f"POL-ENR-PEAK does not state the exact threshold {exact_fr}",
        )
    report.ok(f"threshold {int(round(threshold))} kWh matches the 95th percentile")

    # Summary.
    print(f"\n{report.checks} checks run")
    if report.errors:
        print(f"\n{len(report.errors)} FAILED:\n", file=sys.stderr)
        for error in report.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
