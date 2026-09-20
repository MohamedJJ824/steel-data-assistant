#!/usr/bin/env python
"""Build or refresh the retrieval index in rag.chunks.

Idempotent by content hash: a source whose hash is unchanged is skipped
entirely, so re-running after editing one document re-embeds that document and
nothing else. Embedding is the slow part, and on this hardware it is the reason
this matters.

Usage:
    python scripts/build_index.py            # incremental
    python scripts/build_index.py --rebuild  # drop everything and start over
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from steel_assistant.config import get_settings  # noqa: E402
from steel_assistant.db.engine import superuser_engine  # noqa: E402
from steel_assistant.retrieval.chunkers import Chunk, chunk_file  # noqa: E402
from steel_assistant.retrieval.embedder import get_embedder  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "corpus" / "docs"
CODE_DIR = REPO_ROOT / "corpus" / "legacy_code"

# French stemming and stop words for the documents; `simple` for code, where
# stemming `readings` to `read` would break an identifier match.
TSV_CONFIG = {"doc": "french", "code": "simple"}


def collect_sources() -> list[tuple[Path, str]]:
    """Every file to index, with its source type."""
    sources = [(path, "doc") for path in sorted(DOCS_DIR.glob("*.md"))]
    sources += [(path, "code") for path in sorted(CODE_DIR.glob("*.py"))]
    sources += [(path, "code") for path in sorted(CODE_DIR.glob("*.sql"))]
    return sources


def existing_hashes(conn: object) -> dict[str, str]:
    """Map source_id to the hash currently indexed."""
    rows = conn.execute(  # type: ignore[attr-defined]
        text("SELECT DISTINCT source_id, source_hash FROM rag.chunks")
    ).all()
    return {row[0]: row[1] for row in rows}


def verify_dimension(conn: object, expected: int) -> None:
    """Fail early if the column and the configured model disagree."""
    actual = conn.execute(  # type: ignore[attr-defined]
        text(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'rag.chunks'::regclass AND attname = 'embedding'"
        )
    ).scalar_one()
    if actual != expected:
        raise RuntimeError(
            f"rag.chunks.embedding is VECTOR({actual}) but retrieval.embedding_dim "
            f"is {expected}. Change the column and re-run with --rebuild."
        )


def index_chunks(conn: object, chunks: list[Chunk], source_type: str) -> None:
    """Embed a source's chunks and write them."""
    embedder = get_embedder()
    vectors = embedder.embed_passages([chunk.embed_text() for chunk in chunks])
    config = TSV_CONFIG[source_type]

    payload = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        metadata = {
            **{k: str(v) for k, v in chunk.metadata.items()},
            "tsv_config": config,
        }
        # The heading carries most of a chunk's aboutness. Indexed at weight A
        # against the body's B, it stops twenty near-identical maintenance
        # reports from outranking the one procedure a question is actually
        # about, purely because they all contain the word "défaut".
        if chunk.source_type == "doc":
            heading = " ".join(
                part for part in (str(chunk.metadata.get("title", "")), chunk.section or "") if part
            )
        else:
            heading = f"{chunk.source_id} {chunk.section or ''}"

        payload.append(
            {
                "source_type": chunk.source_type,
                "source_id": chunk.source_id,
                "section": chunk.section,
                "heading": heading,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "content": chunk.content,
                "metadata": json.dumps(metadata, ensure_ascii=False),
                "embedding": str(vector.tolist()),
                "source_hash": str(chunk.metadata.get("source_hash", "")),
                "tsv_config": config,
            }
        )

    conn.execute(  # type: ignore[attr-defined]
        text(
            """
            INSERT INTO rag.chunks
                (source_type, source_id, section, start_line, end_line,
                 content, metadata, embedding, tsv, source_hash)
            VALUES
                (:source_type, :source_id, :section, :start_line, :end_line,
                 :content, CAST(:metadata AS jsonb), CAST(:embedding AS vector),
                 setweight(
                     to_tsvector(CAST(:tsv_config AS regconfig), :heading), 'A'
                 ) || setweight(
                     to_tsvector(CAST(:tsv_config AS regconfig), :content), 'B'
                 ),
                 :source_hash)
            """
        ),
        payload,
    )


def main() -> int:
    """Index every corpus file whose content has changed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true", help="delete every chunk and re-index")
    args = parser.parse_args()

    settings = get_settings().retrieval
    engine = superuser_engine()
    sources = collect_sources()
    print(f"{len(sources)} source files, embedding with {settings.embedding_model}")

    with engine.begin() as conn:
        verify_dimension(conn, settings.embedding_dim)
        if args.rebuild:
            conn.execute(text("TRUNCATE rag.chunks RESTART IDENTITY"))
            print("  rebuilt: existing chunks dropped")
        indexed = existing_hashes(conn)

    started = time.perf_counter()
    changed = skipped = total_chunks = 0

    for path, source_type in sources:
        chunks = chunk_file(
            path,
            **(
                {
                    "max_tokens": settings.chunk_max_tokens,
                    "overlap_tokens": settings.chunk_overlap_tokens,
                }
                if path.suffix == ".md"
                else {"class_split_lines": settings.code_class_split_lines}
                if path.suffix == ".py"
                else {}
            ),
        )
        if not chunks:
            continue
        source_id = chunks[0].source_id
        source_hash = str(chunks[0].metadata.get("source_hash", ""))

        if indexed.get(source_id) == source_hash:
            skipped += 1
            continue

        with engine.begin() as conn:
            conn.execute(text("DELETE FROM rag.chunks WHERE source_id = :sid"), {"sid": source_id})
            index_chunks(conn, chunks, source_type)
        changed += 1
        total_chunks += len(chunks)
        print(f"  {source_id:<22} {len(chunks):>3} chunks")

    elapsed = time.perf_counter() - started

    with engine.connect() as conn:
        counts = dict(
            conn.execute(
                text("SELECT source_type, count(*) FROM rag.chunks GROUP BY source_type")
            ).all()
        )
        missing = conn.execute(
            text("SELECT count(*) FROM rag.chunks WHERE embedding IS NULL OR tsv IS NULL")
        ).scalar_one()

    print(
        f"\n{changed} sources indexed ({total_chunks} chunks), {skipped} unchanged, {elapsed:.1f}s"
    )
    print(f"rag.chunks: {counts.get('doc', 0)} doc, {counts.get('code', 0)} code")
    if missing:
        print(f"WARNING: {missing} chunks are missing an embedding or tsvector")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
