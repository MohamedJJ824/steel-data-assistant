#!/usr/bin/env python
"""Generate docs/EVAL_REPORT.md from actual run results.

Reads `eval/runs/summary.json` and the per-question CSVs. Every number in the
report comes from a run; nothing is estimated. If a configuration has not been
run, it is listed as not run rather than filled in.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = REPO_ROOT / "eval" / "runs"
SUMMARY = RUNS_DIR / "summary.json"
REPORT = REPO_ROOT / "docs" / "EVAL_REPORT.md"

CONFIG_LABELS = {
    "c0": ("C0 baseline", "router", "none", "0", "dense", "off"),
    "c1": ("C1 few-shot", "router", "static", "2", "dense", "off"),
    "c2": ("C2 hybrid", "router", "static", "2", "hybrid", "off"),
    "c3": ("C3 rerank", "router", "dynamic", "2", "hybrid", "on"),
    "c4": ("C4 tool-calling", "tool_calling", "dynamic", "2", "hybrid", "on"),
}

HEADLINE = [
    ("overall_sql_execution_accuracy", "SQL exec. acc."),
    ("overall_sql_valid_rate", "SQL valid"),
    ("overall_routing_accuracy", "Routing"),
    ("overall_routing_superset_rate", "Routing (superset)"),
    ("overall_retrieval_recall_at_5", "Recall@5"),
    ("overall_faithfulness_mean", "Faithfulness"),
    ("overall_answer_correctness_mean", "Correctness"),
    ("overall_refusal_accuracy", "Refusal acc."),
    ("overall_false_refusal_rate", "False refusal"),
    ("overall_number_grounding", "Num. grounding"),
]


def fmt(value: Any, decimals: int = 3) -> str:
    """Format a metric, or an em dash when it was not measured."""
    if value is None:
        return "—"
    if isinstance(value, int | float):
        return f"{value:.{decimals}f}"
    return str(value)


def latest_csv(config: str) -> Path | None:
    """The most recent per-question CSV for a configuration."""
    matches = sorted(RUNS_DIR.glob(f"{config}-*.csv"))
    return matches[-1] if matches else None


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read a per-question CSV."""
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def best_config(summary: dict[str, Any]) -> str | None:
    """The configuration with the highest SQL execution accuracy, then recall."""
    ranked = sorted(
        summary.items(),
        key=lambda item: (
            item[1].get("overall_sql_execution_accuracy") or 0,
            item[1].get("overall_retrieval_recall_at_5") or 0,
            item[1].get("overall_number_grounding") or 0,
        ),
        reverse=True,
    )
    return ranked[0][0] if ranked else None


def failure_analyses(rows: list[dict[str, str]], limit: int = 5) -> list[dict[str, str]]:
    """Pick real failures worth writing up, one per distinct failure mode."""
    failures: list[dict[str, str]] = []
    seen_modes: set[str] = set()

    def add(row: dict[str, str], mode: str, what: str) -> None:
        if mode in seen_modes or len(failures) >= limit:
            return
        seen_modes.add(mode)
        failures.append({**row, "_mode": mode, "_what": what})

    for row in rows:
        if row.get("error"):
            add(row, "crash", "the run raised an exception")
        elif row.get("sql_correct") == "False" and row.get("sql_valid") == "True":
            add(row, "wrong-sql", "the query ran but returned the wrong result")
        elif row.get("sql_valid") == "False":
            add(row, "invalid-sql", "no valid SQL was produced")
        elif row.get("retrieval_hit") == "0.0":
            add(row, "retrieval-miss", "the gold source was not in the top 5")
        elif row.get("category") != "unanswerable" and row.get("refused") == "True":
            add(row, "false-refusal", "an answerable question was declined")
        elif row.get("category") == "unanswerable" and row.get("refused") == "False":
            add(row, "missed-refusal", "an out-of-scope question was answered")
        elif row.get("faithfulness") and float(row["faithfulness"]) <= 3:
            add(row, "unfaithful", "the judge found unsupported claims")
        elif row.get("numbers_checked", "0") != "0" and row.get("numbers_grounded") != row.get(
            "numbers_checked"
        ):
            add(row, "ungrounded-number", "a number was not found in the tool outputs")
    return failures


def hardware_note() -> str:
    """Describe the machine the runs happened on."""
    try:
        cpu = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        cpu = platform.processor()
    try:
        memory_bytes = int(
            subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            ).stdout.strip()
        )
        memory = f"{memory_bytes / 1024**3:.0f} GB RAM"
    except Exception:  # noqa: BLE001
        memory = "unknown RAM"
    return f"{cpu or platform.machine()}, {memory}, {platform.system()} {platform.release()}"


def build_report(summary: dict[str, Any]) -> str:
    """Assemble the markdown report."""
    lines: list[str] = []
    add = lines.append

    add("# Evaluation report\n")
    add(f"Generated {date.today().isoformat()} by `scripts/make_report.py`.")
    add("Every number below comes from an actual run. Nothing is estimated.\n")

    run_configs = [c for c in CONFIG_LABELS if c in summary]
    missing = [c for c in CONFIG_LABELS if c not in summary]

    # ---------------------------------------------------------- setup ----
    add("## Setup\n")
    add(f"- **Hardware**: {hardware_note()}")
    first = summary.get(run_configs[0], {}) if run_configs else {}
    add(
        f"- **Questions**: {first.get('n_questions', '?')} "
        "(18 sql, 12 docs, 10 code, 12 multi, 8 unanswerable; half French, half English)"
    )
    add(
        "- **Models**: see the per-configuration parameters logged in MLflow "
        "(experiment `steel-assistant-eval`)"
    )
    add("")
    add(
        "> **The judge is the model under test.** Only one model fits in memory on "
        "this machine, so `judge_model` is the same model that produced the answers. "
        "It grades its own work, which inflates faithfulness and correctness. The "
        "deterministic metrics — SQL execution accuracy, routing, refusal and number "
        "grounding — are the ones to rely on.\n"
    )

    # -------------------------------------------------------- results ----
    add("## Results by configuration\n")
    add("| Config | Agent | Few-shot | Retries | Retrieval | Rerank |")
    add("|---|---|---|---|---|---|")
    for config, label in CONFIG_LABELS.items():
        mark = "" if config in summary else " *(not run)*"
        add(
            f"| {label[0]}{mark} | {label[1]} | {label[2]} | {label[3]} | {label[4]} | {label[5]} |"
        )
    add("")

    if not run_configs:
        add("No configuration has been run yet. Run `make eval-all`.\n")
        return "\n".join(lines)

    header = "| Metric | " + " | ".join(CONFIG_LABELS[c][0] for c in run_configs) + " |"
    add(header)
    add("|---" * (len(run_configs) + 1) + "|")
    for key, label in HEADLINE:
        cells = [fmt(summary[c].get(key)) for c in run_configs]
        add(f"| {label} | " + " | ".join(cells) + " |")
    for key, label, decimals in [
        ("overall_latency_p50_ms", "Latency p50 (s)", 1),
        ("overall_latency_p95_ms", "Latency p95 (s)", 1),
    ]:
        cells = []
        for config in run_configs:
            value = summary[config].get(key)
            cells.append(fmt(value / 1000 if value else None, decimals))
        add(f"| {label} | " + " | ".join(cells) + " |")
    add(
        "| Wall time (min) | "
        + " | ".join(fmt((summary[c].get("wall_time_s") or 0) / 60, 1) for c in run_configs)
        + " |"
    )
    add("")

    if missing:
        add(f"*Not yet run: {', '.join(CONFIG_LABELS[c][0] for c in missing)}.*\n")

    # ------------------------------------------------- best breakdown ----
    best = best_config(summary)
    if best:
        add(f"## Per-category breakdown — {CONFIG_LABELS[best][0]}\n")
        add("| Category | n | SQL exec. | Recall@5 | Faithfulness | Grounding | p50 (s) |")
        add("|---|---|---|---|---|---|---|")
        for category in ("sql", "docs", "code", "multi", "unanswerable"):
            metrics = summary[best]
            latency = metrics.get(f"{category}_latency_p50_ms")
            csv_path = latest_csv(best)
            n = (
                sum(1 for r in read_rows(csv_path) if r["category"] == category)
                if csv_path
                else "?"
            )
            add(
                f"| {category} | {n} | "
                f"{fmt(metrics.get(f'{category}_sql_execution_accuracy'))} | "
                f"{fmt(metrics.get(f'{category}_retrieval_recall_at_5'))} | "
                f"{fmt(metrics.get(f'{category}_faithfulness_mean'))} | "
                f"{fmt(metrics.get(f'{category}_number_grounding'))} | "
                f"{fmt((latency / 1000) if latency else None, 1)} |"
            )
        add("")

        # ------------------------------------------------- failures ----
        csv_path = latest_csv(best)
        if csv_path:
            rows = read_rows(csv_path)
            add("## Failure analysis\n")
            add(f"Drawn from `{csv_path.relative_to(REPO_ROOT)}`, one per distinct failure mode.\n")
            analyses = failure_analyses(rows)
            if not analyses:
                add("No failures of the tracked kinds occurred in this run.\n")
            for index, row in enumerate(analyses, start=1):
                add(f"### {index}. {row['id']} — {row['_mode']}\n")
                add(f"**Question** ({row['category']}, {row['lang']}): {row['question']}\n")
                add(f"**What happened**: {row['_what']}.")
                if row.get("tools_called") or row.get("expected_tools"):
                    add(
                        f"Tools called: `{row.get('tools_called') or 'none'}`; "
                        f"expected: `{row.get('expected_tools') or 'none'}`."
                    )
                if row.get("sql_generated"):
                    add(f"\n```sql\n{row['sql_generated'][:300]}\n```")
                if row.get("answer"):
                    add(f"\n**Answer given**: {row['answer'][:300]}\n")
                if row.get("error"):
                    add(f"\n**Error**: `{row['error'][:200]}`\n")
                add("")

            # ---------------------------------------------- summary ----
            modes = Counter()
            for row in rows:
                if row.get("error"):
                    modes["run error"] += 1
                if row.get("sql_valid") == "False":
                    modes["no valid SQL"] += 1
                elif row.get("sql_correct") == "False":
                    modes["wrong SQL result"] += 1
                if row.get("retrieval_hit") == "0.0":
                    modes["retrieval miss"] += 1
                if row["category"] != "unanswerable" and row.get("refused") == "True":
                    modes["false refusal"] += 1
                if row["category"] == "unanswerable" and row.get("refused") == "False":
                    modes["missed refusal"] += 1
            if modes:
                add("### Failure counts\n")
                add("| Failure mode | Questions |")
                add("|---|---|")
                for mode, count in modes.most_common():
                    add(f"| {mode} | {count} |")
                add("")

    add("## Reproducing\n")
    add("```bash\nmake up && make seed\nmake eval-all\nmake report\n```\n")
    add(
        "Runs are tracked in MLflow under experiment `steel-assistant-eval`, "
        "with the full configuration as parameters and the per-question CSV as "
        "an artifact.\n"
    )
    return "\n".join(lines)


def main() -> int:
    """Write the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()

    if not SUMMARY.is_file():
        print(f"No results at {SUMMARY}. Run `make eval-all` first.", file=sys.stderr)
        return 1

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_report(summary), encoding="utf-8")
    print(f"wrote {args.out.relative_to(REPO_ROOT)} from {len(summary)} configuration(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
