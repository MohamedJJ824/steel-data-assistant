"""Cross-encoder reranking.

A bi-encoder scores the query and the passage separately, so it never sees them
together. A cross-encoder does, which is more accurate and far slower — hence a
config flag and a reranking pool of only the fused top 20.
"""

from __future__ import annotations

import functools
import threading
from typing import TYPE_CHECKING

from steel_assistant.config import get_settings

if TYPE_CHECKING:  # pragma: no cover
    from sentence_transformers import CrossEncoder

_LOCK = threading.Lock()


class Reranker:
    """Wraps a cross-encoder, loaded lazily."""

    def __init__(self, model_name: str | None = None) -> None:
        """Configure the reranker. The model itself loads on first use."""
        self.model_name = model_name or get_settings().retrieval.reranker_model
        self._model: CrossEncoder | None = None

    @property
    def model(self) -> CrossEncoder:
        """Load the cross-encoder on first use."""
        if self._model is None:
            with _LOCK:
                if self._model is None:
                    from sentence_transformers import CrossEncoder

                    self._model = CrossEncoder(self.model_name)
        return self._model

    def score(self, query: str, passages: list[str]) -> list[float]:
        """Relevance score for each passage against the query."""
        if not passages:
            return []
        pairs = [(query, passage) for passage in passages]
        return [float(score) for score in self.model.predict(pairs)]


@functools.lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    """Process-wide reranker, so the model loads once."""
    return Reranker()
