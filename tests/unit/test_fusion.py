"""Reciprocal Rank Fusion on toy rankings."""

import pytest

from steel_assistant.retrieval.fusion import DEFAULT_K, reciprocal_rank_fusion


def test_single_ranking_is_preserved():
    fused = reciprocal_rank_fusion([["a", "b", "c"]])
    assert [item for item, _ in fused] == ["a", "b", "c"]


def test_agreement_between_rankings_wins():
    """An item ranked second by both beats one ranked first by only one."""
    fused = reciprocal_rank_fusion([["x", "shared"], ["y", "shared"]])
    assert fused[0][0] == "shared"


def test_scores_match_the_formula():
    fused = dict(reciprocal_rank_fusion([["a", "b"], ["b", "a"]], k=60))
    expected = 1 / (DEFAULT_K + 1) + 1 / (DEFAULT_K + 2)
    assert fused["a"] == pytest.approx(expected)
    assert fused["b"] == pytest.approx(expected)


def test_item_in_one_ranking_only_still_scores():
    fused = dict(reciprocal_rank_fusion([["a"], ["b"]]))
    assert fused["a"] == pytest.approx(1 / (DEFAULT_K + 1))
    assert fused["b"] == pytest.approx(1 / (DEFAULT_K + 1))


def test_ties_are_broken_deterministically():
    """Equal scores keep first-appearance order, so runs are reproducible."""
    first = reciprocal_rank_fusion([["a"], ["b"]])
    second = reciprocal_rank_fusion([["a"], ["b"]])
    assert first == second
    assert [item for item, _ in first] == ["a", "b"]


def test_empty_input():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_smaller_k_sharpens_the_top_ranks():
    """A low k makes rank 1 count for much more than rank 2."""
    sharp = dict(reciprocal_rank_fusion([["a", "b"]], k=1))
    flat = dict(reciprocal_rank_fusion([["a", "b"]], k=1000))
    assert sharp["a"] / sharp["b"] > flat["a"] / flat["b"]


def test_dense_and_keyword_disagreement():
    """The realistic case: two branches with one overlapping document."""
    dense = ["doc_a", "doc_b", "doc_c"]
    keyword = ["doc_d", "doc_b", "doc_e"]
    fused = [item for item, _ in reciprocal_rank_fusion([dense, keyword])]
    assert fused[0] == "doc_b"
    assert set(fused) == {"doc_a", "doc_b", "doc_c", "doc_d", "doc_e"}
