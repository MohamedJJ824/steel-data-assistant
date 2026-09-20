"""Runs one configuration over the evaluation set and records the result.

Per-question rows are written to CSV as the run proceeds, so a run interrupted
after forty questions still yields forty usable rows. On this hardware a full
configuration takes the better part of an hour, which makes that worth doing.
"""

from __future__ import annotations

import csv
import json
import time
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from steel_assistant.agent.graph import answer_question
from steel_assistant.config import Settings, get_settings
from steel_assistant.eval.judge import judge_correctness, judge_faithfulness
from steel_assistant.eval.metrics import (
    QuestionOutcome,
    aggregate,
    has_explicit_order,
    is_refusal,
    retrieval_recall_at_k,
    sql_result_matches,
)
from steel_assistant.llm.base import LLMClient

REPO_ROOT = Path(__file__).resolve().parents[3]
QUESTIONS_PATH = REPO_ROOT / "eval" / "questions.jsonl"
GOLD_DIR = REPO_ROOT / "eval" / "gold_results"
RUNS_DIR = REPO_ROOT / "eval" / "runs"

CSV_FIELDS = [
    "id",
    "category",
    "lang",
    "question",
    "tools_called",
    "expected_tools",
    "sql_generated",
    "sql_valid",
    "sql_correct",
    "retrieval_hit",
    "faithfulness",
    "answer_correctness",
    "refused",
    "numbers_checked",
    "numbers_grounded",
    "latency_ms",
    "answer",
    "error",
]


def load_questions(path: Path | None = None) -> list[dict[str, Any]]:
    """Read the evaluation set."""
    path = path or QUESTIONS_PATH
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def load_gold_result(question_id: str) -> dict[str, Any] | None:
    """Read a stored gold result, if the question has one."""
    path = GOLD_DIR / f"{question_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _source_ids(state: dict[str, Any]) -> list[str]:
    """Every source id the agent cited, for the recall metric."""
    return [source.id for source in state.get("sources", [])]


def evaluate_question(
    question: dict[str, Any],
    client: LLMClient,
    settings: Settings,
    *,
    use_judge: bool = True,
) -> QuestionOutcome:
    """Run and score one question."""
    outcome = QuestionOutcome(
        id=question["id"],
        category=question["category"],
        lang=question["lang"],
        expected_tools=question.get("expected_tools", []),
    )

    started = time.perf_counter()
    try:
        state = answer_question(question["question"], client, settings)
    except Exception as exc:  # noqa: BLE001 - one bad question must not stop a run
        outcome.error = str(exc)[:300]
        outcome.latency_ms = int((time.perf_counter() - started) * 1000)
        return outcome
    outcome.latency_ms = int((time.perf_counter() - started) * 1000)

    outcome.answer = state.get("answer", "")
    outcome.tools_called = [tc.tool for tc in state.get("tool_calls", []) if tc.ok]
    outcome.refused = is_refusal(outcome.answer)

    grounding = state.get("grounding") or {}
    outcome.numbers_checked = grounding.get("numbers_checked", 0)
    outcome.numbers_grounded = grounding.get("numbers_grounded", 0)

    # SQL accuracy, against the stored gold result.
    sql_result = state.get("sql_result")
    if sql_result is not None and getattr(sql_result, "sql", None):
        outcome.sql_generated = sql_result.sql
        outcome.sql_valid = bool(sql_result.ok)
        gold = load_gold_result(question["id"])
        if gold is not None and sql_result.ok:
            outcome.sql_correct = sql_result_matches(
                [list(row) for row in sql_result.rows],
                gold["rows"],
                ordered=has_explicit_order(question.get("gold_sql")),
            )
        elif gold is not None:
            outcome.sql_correct = False
    elif question.get("gold_sql"):
        # A question with a gold query whose tool never ran is a failure, not a
        # blank: counting it as neither would flatter the configuration.
        outcome.sql_valid = False
        outcome.sql_correct = False

    # Retrieval recall.
    gold_sources = question.get("gold_sources") or []
    if gold_sources:
        outcome.retrieval_hit = retrieval_recall_at_k(_source_ids(state), gold_sources)

    # Judge scores, for everything except the unanswerable questions, where the
    # deterministic refusal check is the measure.
    if use_judge and question["category"] != "unanswerable" and outcome.answer:
        evidence = state.get("tool_outputs", [])
        if evidence:
            outcome.faithfulness = judge_faithfulness(
                client,
                question["question"],
                outcome.answer,
                evidence,
                model=settings.llm.judge_model,
            ).score
        gold_answer = question.get("gold_answer")
        if gold_answer and gold_answer != "REFUSE":
            outcome.answer_correctness = judge_correctness(
                client,
                question["question"],
                outcome.answer,
                gold_answer,
                model=settings.llm.judge_model,
            ).score

    return outcome


def run_evaluation(
    config_name: str,
    client: LLMClient,
    settings: Settings | None = None,
    *,
    questions: Iterable[dict[str, Any]] | None = None,
    use_judge: bool = True,
    use_mlflow: bool = True,
    progress: bool = True,
) -> tuple[dict[str, Any], list[QuestionOutcome]]:
    """Run one configuration over the evaluation set.

    Args:
        config_name: label for the run, e.g. 'c3'.
        client: the LLM client.
        settings: the configuration under test.
        questions: override the question set, for a smoke run.
        use_judge: run the LLM judge. Off roughly halves the wall time.
        use_mlflow: log to MLflow.
        progress: print a line per question.

    Returns:
        The metrics dictionary and every per-question outcome.
    """
    settings = settings or get_settings()
    question_list = list(questions) if questions is not None else load_questions()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    csv_path = RUNS_DIR / f"{config_name}-{stamp}.csv"

    outcomes: list[QuestionOutcome] = []
    started = time.perf_counter()

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()

        for index, question in enumerate(question_list, start=1):
            outcome = evaluate_question(question, client, settings, use_judge=use_judge)
            outcomes.append(outcome)

            row = asdict(outcome)
            row["question"] = question["question"]
            row["tools_called"] = "|".join(outcome.tools_called)
            row["expected_tools"] = "|".join(outcome.expected_tools)
            row["answer"] = outcome.answer.replace("\n", " ")[:800]
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})
            handle.flush()

            if progress:
                marks = []
                if outcome.sql_correct is not None:
                    marks.append(f"sql={'ok' if outcome.sql_correct else 'X'}")
                if outcome.retrieval_hit is not None:
                    marks.append(f"recall={'ok' if outcome.retrieval_hit else 'X'}")
                if outcome.faithfulness is not None:
                    marks.append(f"faith={outcome.faithfulness:.0f}")
                print(
                    f"  [{index:>2}/{len(question_list)}] {outcome.id} "
                    f"{outcome.category:<12} {outcome.latency_ms / 1000:>5.0f}s "
                    f"{' '.join(marks)}",
                    flush=True,
                )

    elapsed = time.perf_counter() - started

    overall = aggregate(outcomes)
    metrics: dict[str, Any] = {f"overall_{k}": v for k, v in overall.as_dict().items()}
    for category in ("sql", "docs", "code", "multi", "unanswerable"):
        subset = [o for o in outcomes if o.category == category]
        if subset:
            for key, value in aggregate(subset).as_dict().items():
                metrics[f"{category}_{key}"] = value
    metrics["n_questions"] = len(outcomes)
    metrics["n_errors"] = sum(1 for o in outcomes if o.error)
    metrics["wall_time_s"] = round(elapsed, 1)

    if use_mlflow:
        _log_to_mlflow(config_name, settings, metrics, csv_path)

    print(f"\n{config_name}: {len(outcomes)} questions in {elapsed / 60:.1f} min")
    print(f"per-question rows: {csv_path.relative_to(REPO_ROOT)}")
    return metrics, outcomes


def _log_to_mlflow(
    config_name: str, settings: Settings, metrics: dict[str, Any], csv_path: Path
) -> None:
    """Record params, metrics and the per-question CSV in MLflow."""
    try:
        import mlflow
    except ImportError:
        print("  mlflow not installed; skipping tracking")
        return

    try:
        # MLflow 3 raises on a bare ./mlruns file store, so an explicit backend
        # is set rather than relying on the default. An env override still wins.
        import os

        if not os.environ.get("MLFLOW_TRACKING_URI"):
            mlflow.set_tracking_uri(settings.eval.tracking_uri)
        mlflow.set_experiment(settings.eval.experiment_name)
        with mlflow.start_run(run_name=config_name):
            mlflow.log_params(
                {
                    "config": config_name,
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
                }
            )
            mlflow.log_metrics(
                {k: float(v) for k, v in metrics.items() if isinstance(v, int | float)}
            )
            mlflow.log_artifact(str(csv_path))
    except Exception as exc:  # noqa: BLE001 - tracking must not fail a run
        print(f"  mlflow logging failed: {exc}")
