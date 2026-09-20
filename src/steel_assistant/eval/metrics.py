"""Evaluation metrics.

The comparison rules here decide what counts as a correct answer, so they are
written to be defensible rather than lenient:

* result sets are compared order-insensitively unless the gold query has an
  explicit ORDER BY, because otherwise a correct query loses on row order;
* column names are ignored, because `count(*)` and `nb_toles` are the same
  answer;
* floating-point numbers compare with a relative tolerance, because 959636.71
  and 959636.7 are the same answer and float summation is not associative;
* integers compare exactly. The plan specifies a 1e-2 relative tolerance, but
  applying it to a count would accept 405 against a gold of 402. Counts are
  exact, so only floats get the tolerance.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

NUMERIC_TOLERANCE = 1e-2


def _canonical(value: Any) -> Any:
    """Reduce a cell to something comparable across drivers and types."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool):
        return value
    # int stays int: a count is exact, and must not inherit the float tolerance.
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    return str(value).strip()


def _cells_match(left: Any, right: Any, tolerance: float) -> bool:
    """Compare two cells, numerically where both are numbers."""
    left, right = _canonical(left), _canonical(right)

    # Two integers are a count, an id or a row number. They are exact, and the
    # relative tolerance would wave through a count of 405 against a gold of
    # 402 — nearly 1% apart and plainly a different answer.
    if isinstance(left, int) and isinstance(right, int):
        return left == right

    if isinstance(left, int | float) and isinstance(right, int | float):
        left, right = float(left), float(right)
        if math.isnan(left) and math.isnan(right):
            return True
        scale = max(abs(left), abs(right), 1e-9)
        return abs(left - right) / scale <= tolerance

    return left == right


def _row_key(row: list[Any]) -> tuple:
    """A hashable form of a row, with floats rounded so near-equal rows collide."""
    key = []
    for cell in row:
        value = _canonical(cell)
        if isinstance(value, float):
            value = round(value, 6)
        key.append(value)
    return tuple(key)


def has_explicit_order(sql: str | None) -> bool:
    """True when the gold query pins row order, making order significant."""
    return bool(sql) and re.search(r"\border\s+by\b", sql, re.IGNORECASE) is not None


def sql_result_matches(
    predicted: list[list[Any]] | None,
    gold: list[list[Any]] | None,
    *,
    ordered: bool = False,
    tolerance: float = NUMERIC_TOLERANCE,
) -> bool:
    """Compare two result sets.

    Args:
        predicted: rows the generated query returned.
        gold: rows the gold query returned.
        ordered: compare row order too. Set when the gold query has ORDER BY.
        tolerance: relative tolerance for numeric cells.

    Returns:
        True when the two result sets carry the same answer.
    """
    if predicted is None or gold is None:
        return False
    if len(predicted) != len(gold):
        return False
    if not gold:
        return True

    # A generated query may select extra columns (an id alongside a count) and
    # still be right, so compare on the gold query's column count.
    width = len(gold[0])
    if any(len(row) < width for row in predicted):
        return False
    trimmed = [row[:width] for row in predicted]

    if ordered:
        return all(
            all(_cells_match(p, g, tolerance) for p, g in zip(prow, grow, strict=True))
            for prow, grow in zip(trimmed, gold, strict=True)
        )

    # Unordered: multiset comparison, so duplicates still have to match.
    if Counter(_row_key(row) for row in trimmed) == Counter(_row_key(row) for row in gold):
        return True
    # Fall back to a tolerance-aware pairing for floats that round differently.
    remaining = list(gold)
    for row in trimmed:
        for index, candidate in enumerate(remaining):
            if all(_cells_match(p, g, tolerance) for p, g in zip(row, candidate, strict=True)):
                remaining.pop(index)
                break
        else:
            return False
    return not remaining


def tools_match(predicted: list[str], expected: list[str]) -> bool:
    """Exact set equality between tools called and tools expected."""
    return set(predicted) == set(expected)


def tools_superset(predicted: list[str], expected: list[str]) -> bool:
    """Every expected tool was called; extras allowed."""
    return set(expected).issubset(set(predicted))


def retrieval_recall_at_k(sources: list[str], gold_sources: list[str]) -> float | None:
    """1.0 when at least one gold source is among the retrieved ones.

    Returns None when the question names no gold source, so questions without
    one are excluded from the average rather than counted as successes.
    """
    if not gold_sources:
        return None
    retrieved = {str(source) for source in sources}
    return 1.0 if any(gold in retrieved for gold in gold_sources) else 0.0


REFUSAL_MARKERS = (
    "ne peux pas",
    "ne peut pas",
    "hors du périmètre",
    "hors périmètre",
    "pas en mesure",
    "ne dispose pas",
    "n'est pas disponible",
    "je ne peux",
    "cannot answer",
    "can't answer",
    "outside the scope",
    "out of scope",
    "not able to",
    "do not have",
    "don't have",
    "not available",
    "no information",
    "pas d'information",
    "aucune information",
)


def is_refusal(answer: str) -> bool:
    """True when an answer declines rather than answers.

    Deliberately a marker list rather than a judge call: refusal accuracy is
    measured across every configuration, and a deterministic check keeps that
    metric comparable between runs instead of varying with the judge's mood.
    """
    lowered = answer.lower()
    return any(marker in lowered for marker in REFUSAL_MARKERS)


@dataclass
class CategoryMetrics:
    """Aggregated results for one category, or for everything."""

    n: int = 0
    sql_execution_accuracy: float | None = None
    sql_valid_rate: float | None = None
    routing_accuracy: float | None = None
    routing_superset_rate: float | None = None
    retrieval_recall_at_5: float | None = None
    faithfulness_mean: float | None = None
    faithfulness_at_least_4: float | None = None
    answer_correctness_mean: float | None = None
    refusal_accuracy: float | None = None
    false_refusal_rate: float | None = None
    number_grounding: float | None = None
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None

    def as_dict(self) -> dict[str, float]:
        """Non-null metrics, for MLflow."""
        return {
            key: value for key, value in self.__dict__.items() if value is not None and key != "n"
        }


def _mean(values: list[float]) -> float | None:
    """Mean, or None for an empty list."""
    return sum(values) / len(values) if values else None


def percentile(values: list[float], fraction: float) -> float | None:
    """Linear-interpolated percentile."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    low = int(math.floor(position))
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


@dataclass
class QuestionOutcome:
    """Everything recorded for one evaluated question."""

    id: str
    category: str
    lang: str
    tools_called: list[str] = field(default_factory=list)
    expected_tools: list[str] = field(default_factory=list)
    sql_generated: str | None = None
    sql_valid: bool | None = None
    sql_correct: bool | None = None
    retrieval_hit: float | None = None
    faithfulness: float | None = None
    answer_correctness: float | None = None
    refused: bool = False
    numbers_checked: int = 0
    numbers_grounded: int = 0
    latency_ms: int = 0
    answer: str = ""
    error: str | None = None


def aggregate(outcomes: list[QuestionOutcome]) -> CategoryMetrics:
    """Roll a set of outcomes up into metrics."""
    if not outcomes:
        return CategoryMetrics()

    metrics = CategoryMetrics(n=len(outcomes))

    sql_correct = [o.sql_correct for o in outcomes if o.sql_correct is not None]
    if sql_correct:
        metrics.sql_execution_accuracy = _mean([float(v) for v in sql_correct])
    sql_valid = [o.sql_valid for o in outcomes if o.sql_valid is not None]
    if sql_valid:
        metrics.sql_valid_rate = _mean([float(v) for v in sql_valid])

    answerable = [o for o in outcomes if o.category != "unanswerable"]
    if answerable:
        metrics.routing_accuracy = _mean(
            [float(tools_match(o.tools_called, o.expected_tools)) for o in answerable]
        )
        metrics.routing_superset_rate = _mean(
            [float(tools_superset(o.tools_called, o.expected_tools)) for o in answerable]
        )

    recall = [o.retrieval_hit for o in outcomes if o.retrieval_hit is not None]
    if recall:
        metrics.retrieval_recall_at_5 = _mean(recall)

    faithfulness = [o.faithfulness for o in outcomes if o.faithfulness is not None]
    if faithfulness:
        metrics.faithfulness_mean = _mean(faithfulness)
        metrics.faithfulness_at_least_4 = _mean([float(v >= 4) for v in faithfulness])

    correctness = [o.answer_correctness for o in outcomes if o.answer_correctness is not None]
    if correctness:
        metrics.answer_correctness_mean = _mean(correctness)

    unanswerable = [o for o in outcomes if o.category == "unanswerable"]
    if unanswerable:
        metrics.refusal_accuracy = _mean([float(o.refused) for o in unanswerable])
    if answerable:
        metrics.false_refusal_rate = _mean([float(o.refused) for o in answerable])

    checked = sum(o.numbers_checked for o in outcomes)
    if checked:
        metrics.number_grounding = sum(o.numbers_grounded for o in outcomes) / checked

    latencies = [float(o.latency_ms) for o in outcomes if o.latency_ms]
    metrics.latency_p50_ms = percentile(latencies, 0.50)
    metrics.latency_p95_ms = percentile(latencies, 0.95)

    return metrics
