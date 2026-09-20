"""Metric comparison rules.

These decide what counts as correct, so a mistake here silently changes every
number in the report.
"""

import pytest

from steel_assistant.eval.metrics import (
    QuestionOutcome,
    aggregate,
    has_explicit_order,
    is_refusal,
    percentile,
    retrieval_recall_at_k,
    sql_result_matches,
    tools_match,
    tools_superset,
)

# --------------------------------------------------------- result matching --


def test_identical_results_match():
    assert sql_result_matches([[402]], [[402]])


def test_row_order_ignored_by_default():
    assert sql_result_matches([["b", 2], ["a", 1]], [["a", 1], ["b", 2]])


def test_row_order_enforced_when_requested():
    assert not sql_result_matches([["b", 2], ["a", 1]], [["a", 1], ["b", 2]], ordered=True)


def test_order_by_detected_in_gold_sql():
    assert has_explicit_order("SELECT x FROM t ORDER BY x")
    assert has_explicit_order("select x from t order by x desc")
    assert not has_explicit_order("SELECT x FROM t")
    assert not has_explicit_order(None)


def test_float_tolerance():
    """Float summation is not associative; 959636.71 and 959636.7 are one answer."""
    assert sql_result_matches([[959636.7100000565]], [[959636.7]])
    assert not sql_result_matches([[959636.7]], [[900000.0]])


def test_counts_compare_exactly():
    """A 1% tolerance would accept 405 against 402. A count is exact."""
    assert sql_result_matches([[402]], [[402]])
    assert not sql_result_matches([[405]], [[402]])
    assert not sql_result_matches([[1940]], [[1941]])


def test_decimal_and_float_compare_equal():
    from decimal import Decimal

    assert sql_result_matches([[Decimal("122.4184782608695652")]], [[122.41847826086957]])


def test_column_name_is_irrelevant():
    """Only values are compared; count(*) and nb_toles are the same answer."""
    assert sql_result_matches([[7]], [[7]])


def test_extra_columns_are_tolerated():
    """Selecting an id alongside the count is still the right answer."""
    assert sql_result_matches([["L1", 267, "extra"]], [["L1", 267]])


def test_missing_column_is_not_tolerated():
    assert not sql_result_matches([["L1"]], [["L1", 267]])


def test_row_count_must_match():
    assert not sql_result_matches([[1], [2]], [[1]])


def test_duplicates_must_match():
    assert not sql_result_matches([[1], [1]], [[1], [2]])


def test_none_is_never_a_match():
    assert not sql_result_matches(None, [[1]])
    assert not sql_result_matches([[1]], None)


def test_two_empty_results_match():
    assert sql_result_matches([], [])


# ------------------------------------------------------------------ tools --


def test_tools_match_is_set_equality():
    assert tools_match(["sql_query"], ["sql_query"])
    assert tools_match(["b", "a"], ["a", "b"])
    assert not tools_match(["sql_query", "search_docs"], ["sql_query"])


def test_superset_allows_extras():
    assert tools_superset(["sql_query", "search_docs"], ["sql_query"])
    assert not tools_superset(["search_docs"], ["sql_query"])


# -------------------------------------------------------------- retrieval --


def test_recall_hits_and_misses():
    assert retrieval_recall_at_k(["PROC-FLT-ZSCR", "x"], ["PROC-FLT-ZSCR"]) == 1.0
    assert retrieval_recall_at_k(["x"], ["PROC-FLT-ZSCR"]) == 0.0


def test_recall_is_none_without_a_gold_source():
    """None excludes the question from the average rather than scoring it 1.0."""
    assert retrieval_recall_at_k(["x"], []) is None


# --------------------------------------------------------------- refusals --


@pytest.mark.parametrize(
    "answer",
    [
        "Je ne peux pas répondre à cette question.",
        "Cette question est hors du périmètre de l'assistant.",
        "I cannot answer that from the plant data.",
        "That is outside the scope of this assistant.",
        "Cette information n'est pas disponible.",
    ],
)
def test_refusals_detected(answer):
    assert is_refusal(answer)


@pytest.mark.parametrize(
    "answer",
    ["Il y a 402 tôles avec un défaut Bumps.", "The total is 959636.7 kWh."],
)
def test_real_answers_are_not_refusals(answer):
    assert not is_refusal(answer)


# ------------------------------------------------------------ aggregation --


def test_percentile():
    assert percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert percentile([10], 0.95) == 10
    assert percentile([], 0.5) is None


def test_refusal_metrics_split_answerable_from_unanswerable():
    outcomes = [
        QuestionOutcome(id="a", category="unanswerable", lang="fr", refused=True),
        QuestionOutcome(id="b", category="unanswerable", lang="en", refused=False),
        QuestionOutcome(id="c", category="sql", lang="fr", refused=True),
        QuestionOutcome(id="d", category="sql", lang="en", refused=False),
    ]
    metrics = aggregate(outcomes)
    assert metrics.refusal_accuracy == pytest.approx(0.5)
    assert metrics.false_refusal_rate == pytest.approx(0.5)


def test_routing_excludes_unanswerable():
    """An unanswerable question expects no tools, which would skew routing."""
    outcomes = [
        QuestionOutcome(
            id="a",
            category="sql",
            lang="fr",
            tools_called=["sql_query"],
            expected_tools=["sql_query"],
        ),
        QuestionOutcome(
            id="b", category="unanswerable", lang="fr", tools_called=[], expected_tools=[]
        ),
    ]
    metrics = aggregate(outcomes)
    assert metrics.n == 2
    assert metrics.routing_accuracy == pytest.approx(1.0)


def test_grounding_is_pooled_not_averaged_per_question():
    """One answer with 10 numbers should weigh more than one with a single number."""
    outcomes = [
        QuestionOutcome(id="a", category="sql", lang="fr", numbers_checked=10, numbers_grounded=5),
        QuestionOutcome(id="b", category="sql", lang="fr", numbers_checked=1, numbers_grounded=1),
    ]
    assert aggregate(outcomes).number_grounding == pytest.approx(6 / 11)


def test_empty_aggregation_is_safe():
    assert aggregate([]).n == 0


def test_faithfulness_threshold():
    outcomes = [
        QuestionOutcome(id="a", category="docs", lang="fr", faithfulness=5.0),
        QuestionOutcome(id="b", category="docs", lang="fr", faithfulness=3.0),
    ]
    metrics = aggregate(outcomes)
    assert metrics.faithfulness_mean == pytest.approx(4.0)
    assert metrics.faithfulness_at_least_4 == pytest.approx(0.5)
