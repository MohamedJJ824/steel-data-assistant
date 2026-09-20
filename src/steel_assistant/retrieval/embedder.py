"""Sentence embeddings for indexing and querying.

The e5 family requires asymmetric prefixes — "query: " on the question and
"passage: " on the indexed text. Getting this wrong degrades retrieval quietly
rather than loudly, so both prefixes live in config and are applied here rather
than by callers. bge-m3 needs neither, so the prefixes are configurable to "".
"""

from __future__ import annotations

import functools
import threading
from typing import TYPE_CHECKING

import numpy as np

from steel_assistant.config import get_settings

if TYPE_CHECKING:  # pragma: no cover
    from sentence_transformers import SentenceTransformer

_LOCK = threading.Lock()


class Embedder:
    """Wraps a sentence-transformers model with the configured prefixes."""

    def __init__(
        self,
        model_name: str | None = None,
        *,
        query_prefix: str | None = None,
        passage_prefix: str | None = None,
        expected_dim: int | None = None,
    ) -> None:
        """Configure the embedder. The model itself loads lazily."""
        settings = get_settings().retrieval
        self.model_name = model_name or settings.embedding_model
        self.query_prefix = settings.query_prefix if query_prefix is None else query_prefix
        self.passage_prefix = settings.passage_prefix if passage_prefix is None else passage_prefix
        self.expected_dim = expected_dim or settings.embedding_dim
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Load the model on first use.

        Deferred because importing sentence-transformers pulls in torch, which
        costs seconds and a few hundred megabytes. Unit tests that only touch
        chunking should not pay that.
        """
        if self._model is None:
            with _LOCK:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    model = SentenceTransformer(self.model_name)
                    # Renamed in sentence-transformers 6.x; support both so a
                    # pinned older version still works.
                    get_dim = (
                        getattr(model, "get_embedding_dimension", None)
                        or model.get_sentence_embedding_dimension
                    )
                    actual = get_dim()
                    if actual != self.expected_dim:
                        raise RuntimeError(
                            f"{self.model_name} produces {actual}-dimensional vectors but "
                            f"retrieval.embedding_dim is {self.expected_dim}. Update the "
                            "config and the rag.chunks.embedding column together, then "
                            "rebuild the index."
                        )
                    self._model = model
        return self._model

    def embed_passages(self, texts: list[str], *, batch_size: int = 16) -> np.ndarray:
        """Embed text for storage. Returns L2-normalised vectors."""
        prefixed = [f"{self.passage_prefix}{text}" for text in texts]
        return self.model.encode(
            prefixed,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

    def embed_query(self, text: str) -> np.ndarray:
        """Embed one question. Returns an L2-normalised vector."""
        return self.model.encode(
            f"{self.query_prefix}{text}",
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

    def embed_queries(self, texts: list[str], *, batch_size: int = 16) -> np.ndarray:
        """Embed several questions at once, for the dynamic few-shot selector."""
        prefixed = [f"{self.query_prefix}{text}" for text in texts]
        return self.model.encode(
            prefixed,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )


@functools.lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Process-wide embedder, so the model loads once."""
    return Embedder()
