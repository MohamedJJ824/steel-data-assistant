"""Reciprocal Rank Fusion.

RRF combines rankings without needing their scores to be comparable, which
matters here because cosine distance and ts_rank_cd are on unrelated scales.
Normalising them against each other would mean picking a weighting with no
principled basis; RRF only uses positions.

    score(d) = sum over rankings of 1 / (k + rank(d))

k = 60 is the value from the original paper and damps the influence of the very
top positions, so one ranking cannot dominate on its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")

DEFAULT_K = 60


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[T]], *, k: int = DEFAULT_K
) -> list[tuple[T, float]]:
    """Fuse several ranked lists into one.

    Args:
        rankings: ranked lists, best first. Items are compared by equality, so
            they must be hashable — an id, not a row object.
        k: the RRF damping constant.

    Returns:
        (item, score) pairs sorted by descending score. Ties keep the order of
        first appearance, so the result is deterministic.
    """
    scores: dict[T, float] = {}
    first_seen: dict[T, int] = {}
    counter = 0

    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            if item not in first_seen:
                first_seen[item] = counter
                counter += 1

    return sorted(scores.items(), key=lambda pair: (-pair[1], first_seen[pair[0]]))
