#!/usr/bin/env python
"""Recompute metrics from stored per-question results.

Used when a scoring rule changes and re-running every configuration would cost
hours. It re-derives refusal from the stored answer text with the current
detector and recomputes every aggregate; all other per-question outcomes were
already recorded by the run and are read back unchanged.

This re-scores; it does not re-run. The answers are exactly those the agent
produced.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from steel_assistant.eval.metrics import (  # noqa: E402
    QuestionOutcome,
    aggregate,
    is_refusal,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = REPO_ROOT / "eval" / "runs"


def _optional_bool(value: str) -> bool | None:
    return None if value == "" else value == "True"


def _optional_float(value: str) -> float | None:
    return None if value == "" else float(value)


def load_outcomes(path: Path) -> list[QuestionOutcome]:
    """Rebuild outcomes from a per-question CSV, re-deriving refusal."""
    outcomes = []
    for row in csv.DictReader(path.open(encoding="utf-8")):
        outcomes.append(
            QuestionOutcome(
                id=row["id"],
                category=row["category"],
                lang=row["lang"],
                tools_called=[t for t in row["tools_called"].split("|") if t],
                expected_tools=[t for t in row["expected_tools"].split("|") if t],
                sql_generated=row["sql_generated"] or None,
                sql_valid=_optional_bool(row["sql_valid"]),
                sql_correct=_optional_bool(row["sql_correct"]),
                retrieval_hit=_optional_float(row["retrieval_hit"]),
                faithfulness=_optional_float(row["faithfulness"]),
                answer_correctness=_optional_float(row["answer_correctness"]),
                refused=is_refusal(row["answer"]),
                numbers_checked=int(row["numbers_checked"] or 0),
                numbers_grounded=int(row["numbers_grounded"] or 0),
                latency_ms=int(row["latency_ms"] or 0),
                answer=row["answer"],
                error=row["error"] or None,
            )
        )
    return outcomes


CONFIG_FILES = {
    "c0": "c0_baseline.yaml",
    "c1": "c1_fewshot.yaml",
    "c2": "c2_hybrid.yaml",
    "c3": "c3_rerank.yaml",
    "c4": "c4_tool_calling.yaml",
}


def log_to_mlflow(config: str, metrics: dict, csv_path: Path) -> bool:
    """Record a re-scored run in MLflow.

    Used to backfill: MLflow 3 rejects a bare ./mlruns file store, so tracking
    failed silently during the original runs while the evaluation itself
    succeeded. The metrics logged here are computed from exactly the answers
    those runs produced.
    """
    try:
        import mlflow

        from steel_assistant.config import load_config
    except ImportError:
        print("  mlflow not installed; skipping")
        return False

    config_path = REPO_ROOT / "config" / "eval_configs" / CONFIG_FILES[config]
    settings = load_config(config_path)
    try:
        if not os.environ.get("MLFLOW_TRACKING_URI"):
            mlflow.set_tracking_uri(settings.eval.tracking_uri)
        mlflow.set_experiment(settings.eval.experiment_name)
        with mlflow.start_run(run_name=config):
            mlflow.log_params(
                {
                    "config": config,
                    "agent_mode": settings.agent.mode,
                    "sql_fewshot": settings.sql.fewshot,
                    "sql_max_retries": settings.sql.max_retries,
                    "retrieval_mode": settings.retrieval.mode,
                    "rerank": settings.retrieval.rerank,
                    "embedding_model": settings.retrieval.embedding_model,
                    "agent_model": settings.llm.agent_model,
                    "sql_model": settings.llm.sql_model,
                    "judge_model": settings.llm.judge_model,
                    "llm_backend": settings.llm.backend,
                    "scored_by": "scripts/rescore.py",
                }
            )
            mlflow.log_metrics(
                {k: float(v) for k, v in metrics.items() if isinstance(v, int | float)}
            )
            mlflow.log_artifact(str(csv_path))
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  mlflow logging failed: {exc}")
        return False


def main() -> int:
    """Rewrite summary.json from the latest CSV of each configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mlflow", action="store_true", help="also log each re-scored run to MLflow"
    )
    args = parser.parse_args()

    summary_path = RUNS_DIR / "summary.json"
    existing = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    logged = 0

    for config in sorted({Path(p).name[:2] for p in glob.glob(str(RUNS_DIR / "c*.csv"))}):
        matches = sorted(RUNS_DIR.glob(f"{config}-*.csv"))
        if not matches:
            continue
        path = matches[-1]
        outcomes = load_outcomes(path)

        overall = aggregate(outcomes)
        metrics = {f"overall_{k}": v for k, v in overall.as_dict().items()}
        for category in ("sql", "docs", "code", "multi", "unanswerable"):
            subset = [o for o in outcomes if o.category == category]
            if subset:
                for key, value in aggregate(subset).as_dict().items():
                    metrics[f"{category}_{key}"] = value
        metrics["n_questions"] = len(outcomes)
        metrics["n_errors"] = sum(1 for o in outcomes if o.error)
        # Wall time is a property of the run, not of the scoring; keep it.
        metrics["wall_time_s"] = existing.get(config, {}).get("wall_time_s", 0)

        before = existing.get(config, {}).get("overall_refusal_accuracy")
        after = metrics.get("overall_refusal_accuracy")
        note = f"  refusal_accuracy {before} -> {after}" if before != after else ""
        print(f"{config}: {len(outcomes)} questions from {path.name}{note}")
        existing[config] = metrics
        if args.mlflow and config in CONFIG_FILES:
            logged += log_to_mlflow(config, metrics, path)

    summary_path.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")
    print(f"\nrewrote {summary_path.relative_to(REPO_ROOT)}")
    if args.mlflow:
        print(f"logged {logged} run(s) to MLflow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
