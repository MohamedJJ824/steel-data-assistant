"""Hybrid retrieval over rag.chunks.

Two branches, fused:

* **Dense** — cosine distance over the pgvector HNSW index. Finds paraphrases
  and cross-language matches, which matters because a French question may need
  to retrieve an English identifier out of the code corpus.
* **Keyword** — PostgreSQL full-text ranking. Finds the exact token, which
  dense retrieval is unreliable at: an embedding of `K_Scratch` sits very close
  to one of `Z_Scratch`, and a user asking about one does not want the other.

Neither is sufficient alone, which is why `retrieval.mode` defaults to hybrid
and the dense-only path exists mainly as an evaluation baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Engine

from steel_assistant.config import get_settings
from steel_assistant.db.engine import app_engine
from steel_assistant.retrieval.embedder import Embedder, get_embedder
from steel_assistant.retrieval.fusion import reciprocal_rank_fusion

SourceType = Literal["doc", "code"]


@dataclass(slots=True)
class SearchHit:
    """One retrieved chunk, with everything a citation needs."""

    chunk_id: int
    source_type: str
    source_id: str
    section: str | None
    content: str
    metadata: dict[str, Any]
    start_line: int | None = None
    end_line: int | None = None
    score: float = 0.0
    dense_rank: int | None = None
    keyword_rank: int | None = None

    def citation(self) -> str:
        """Render the citation form this source type uses."""
        if self.source_type == "doc":
            return f"[{self.source_id} §{self.section}]" if self.section else f"[{self.source_id}]"
        if self.start_line is not None:
            return f"{self.source_id}:L{self.start_line}-L{self.end_line}"
        return self.source_id


def _filter_clause(filters: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """Build a JSONB metadata filter, e.g. doc_type or fault_code."""
    if not filters:
        return "", {}
    clauses = []
    params: dict[str, Any] = {}
    for index, (key, value) in enumerate(filters.items()):
        param = f"filter_{index}"
        clauses.append(f"c.metadata ->> '{key}' = :{param}")
        params[param] = str(value)
    return " AND " + " AND ".join(clauses), params


def _dense_search(
    conn: Any,
    query_vector: list[float],
    source_type: SourceType,
    limit: int,
    filters: dict[str, Any] | None,
) -> list[tuple[int, float]]:
    """Top-N chunk ids by cosine distance."""
    clause, params = _filter_clause(filters)
    rows = conn.execute(
        text(
            f"""
            SELECT c.id, c.embedding <=> CAST(:qv AS vector) AS distance
            FROM rag.chunks c
            WHERE c.source_type = :source_type
              AND c.embedding IS NOT NULL{clause}
            ORDER BY distance
            LIMIT :limit
            """
        ),
        {"qv": str(query_vector), "source_type": source_type, "limit": limit, **params},
    ).all()
    return [(row[0], float(row[1])) for row in rows]


def _keyword_search(
    conn: Any,
    query: str,
    source_type: SourceType,
    limit: int,
    filters: dict[str, Any] | None,
) -> list[tuple[int, float]]:
    """Top-N chunk ids by full-text rank.

    `websearch_to_tsquery` is used rather than `plainto_tsquery` because it
    tolerates the punctuation and quoting a user actually types. The text search
    configuration is stored per row at index time — French for documents,
    `simple` for code — so it is read back from the row rather than assumed.

    The `&` to `|` rewrite matters. `websearch_to_tsquery` joins every term with
    AND, so a natural-language question returns nothing unless all of its words
    appear in the same chunk: "défaut Z_Scratch actions immédiates" matched zero
    chunks, silently reducing hybrid search to dense-only. Under OR it matches
    133, with the correct procedure at keyword rank 15 — inside the fusion
    window, which is what RRF needs to combine the two branches. Single-term
    queries such as `K_Scratch` are unaffected: there is no `&` to rewrite.
    """
    clause, params = _filter_clause(filters)
    rows = conn.execute(
        text(
            f"""
            WITH q AS (
                SELECT id,
                       replace(
                           websearch_to_tsquery(
                               (metadata ->> 'tsv_config')::regconfig, :query
                           )::text,
                           '&', '|'
                       )::tsquery AS tq
                FROM rag.chunks
                WHERE source_type = :source_type
            )
            SELECT c.id, ts_rank_cd(c.tsv, q.tq) AS rank
            FROM rag.chunks c
            JOIN q ON q.id = c.id
            WHERE c.source_type = :source_type
              AND q.tq IS NOT NULL
              AND c.tsv @@ q.tq{clause}
            ORDER BY rank DESC
            LIMIT :limit
            """
        ),
        {"query": query, "source_type": source_type, "limit": limit, **params},
    ).all()
    return [(row[0], float(row[1])) for row in rows]


def _load_chunks(conn: Any, chunk_ids: list[int]) -> dict[int, SearchHit]:
    """Fetch the full rows for a set of ids."""
    if not chunk_ids:
        return {}
    rows = conn.execute(
        text(
            """
            SELECT id, source_type, source_id, section, start_line, end_line,
                   content, metadata
            FROM rag.chunks WHERE id = ANY(:ids)
            """
        ),
        {"ids": chunk_ids},
    ).all()
    return {
        row[0]: SearchHit(
            chunk_id=row[0],
            source_type=row[1],
            source_id=row[2],
            section=row[3],
            start_line=row[4],
            end_line=row[5],
            content=row[6],
            metadata=row[7] or {},
        )
        for row in rows
    }


def hybrid_search(
    query: str,
    source_type: SourceType,
    *,
    k: int | None = None,
    filters: dict[str, Any] | None = None,
    engine: Engine | None = None,
    embedder: Embedder | None = None,
    mode: str | None = None,
    rerank: bool | None = None,
) -> list[SearchHit]:
    """Retrieve the top k chunks for a query.

    Args:
        query: the user's question, in any language.
        source_type: 'doc' or 'code'.
        k: how many hits to return. Defaults to retrieval.top_k.
        filters: exact-match metadata filters, e.g. {'doc_type': 'procedure'}.
        engine: database engine. Defaults to the app role's.
        embedder: embedding model. Defaults to the process-wide one.
        mode: 'dense' or 'hybrid'. Defaults to retrieval.mode.
        rerank: whether to apply the cross-encoder. Defaults to retrieval.rerank.

    Returns:
        Hits ordered best first.
    """
    settings = get_settings().retrieval
    k = k or settings.top_k
    mode = mode or settings.mode
    rerank = settings.rerank if rerank is None else rerank
    candidates = settings.candidates_per_branch
    engine = engine or app_engine()
    embedder = embedder or get_embedder()

    query_vector = embedder.embed_query(query).tolist()

    with engine.connect() as conn:
        dense = _dense_search(conn, query_vector, source_type, candidates, filters)
        keyword: list[tuple[int, float]] = []
        if mode == "hybrid":
            keyword = _keyword_search(conn, query, source_type, candidates, filters)

        dense_ids = [chunk_id for chunk_id, _ in dense]
        keyword_ids = [chunk_id for chunk_id, _ in keyword]

        rankings = [dense_ids] if mode == "dense" else [dense_ids, keyword_ids]
        fused = reciprocal_rank_fusion(rankings, k=settings.rrf_k)

        # Rerank a wider slice than we return, so the cross-encoder has room to
        # move a genuinely better chunk up from position 8 into the top 5.
        pool = fused[: candidates if rerank else k]
        hits_by_id = _load_chunks(conn, [chunk_id for chunk_id, _ in pool])

    dense_positions = {chunk_id: i + 1 for i, chunk_id in enumerate(dense_ids)}
    keyword_positions = {chunk_id: i + 1 for i, chunk_id in enumerate(keyword_ids)}

    hits: list[SearchHit] = []
    for chunk_id, score in pool:
        hit = hits_by_id.get(chunk_id)
        if hit is None:
            continue
        hit.score = score
        hit.dense_rank = dense_positions.get(chunk_id)
        hit.keyword_rank = keyword_positions.get(chunk_id)
        hits.append(hit)

    if rerank and hits:
        hits = _apply_rerank(query, hits)

    return hits[:k]


def _apply_rerank(query: str, hits: list[SearchHit]) -> list[SearchHit]:
    """Reorder hits with a cross-encoder, falling back to the fused order."""
    from steel_assistant.retrieval.reranker import get_reranker

    try:
        reranker = get_reranker()
    except Exception:  # noqa: BLE001 - a missing reranker must not break retrieval
        return hits
    scores = reranker.score(query, [hit.content for hit in hits])
    for hit, score in zip(hits, scores, strict=True):
        hit.score = float(score)
    return sorted(hits, key=lambda hit: hit.score, reverse=True)
