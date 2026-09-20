"""Chunkers for the two corpora.

Documents split on markdown headings, code splits on its AST. Both record
enough provenance for a citation: a document chunk knows its heading path, a
code chunk knows its exact line range. Those citations are a graded output, so
the line numbers have to be right, not approximately right.
"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter
import sqlglot

# Rough token estimate. A real tokenizer would be more accurate, but chunk size
# only needs to be in the right range and this avoids loading one just to split.
CHARS_PER_TOKEN = 4

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_SQL_NAME = re.compile(r"^--\s*name:\s*(\S+)", re.MULTILINE)


@dataclass(slots=True)
class Chunk:
    """One indexable unit of a document or a source file."""

    source_type: str
    source_id: str
    content: str
    section: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def embed_text(self) -> str:
        """The text actually embedded.

        The heading path or the symbol name is prepended so that a chunk taken
        out of its file still carries what it is about. Without this, a function
        body full of generic variable names embeds almost identically to every
        other function body.
        """
        if self.source_type == "doc":
            title = self.metadata.get("title", self.source_id)
            prefix = f"{title} > {self.section}" if self.section else str(title)
            return f"{prefix}\n\n{self.content}"
        symbol = self.section or "module"
        return f"File: {self.source_id}\nSymbol: {symbol}\n\n{self.content}"


def file_hash(text: str) -> str:
    """Content hash, used to skip re-indexing unchanged sources."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _split_long(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Split text that exceeds the size budget, on paragraph boundaries."""
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return [text]

    overlap_chars = overlap_tokens * CHARS_PER_TOKEN
    parts: list[str] = []
    paragraphs = text.split("\n\n")
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars and current:
            parts.append(current)
            # Carry the tail of the previous piece so a sentence spanning the
            # boundary is still retrievable from one side of it.
            tail = current[-overlap_chars:] if overlap_chars else ""
            current = f"{tail}\n\n{paragraph}" if tail else paragraph
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


# ----------------------------------------------------------------- markdown --


def chunk_markdown(path: Path, *, max_tokens: int = 500, overlap_tokens: int = 50) -> list[Chunk]:
    """Split a markdown document on its headings.

    Front matter becomes chunk metadata, and the heading path ("Procédure >
    Actions immédiates") becomes the section, which is what an answer cites.
    """
    raw = path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)
    metadata = dict(post.metadata)
    doc_id = str(metadata.get("doc_id") or path.stem)
    source_hash = file_hash(raw)

    lines = post.content.splitlines()
    sections: list[tuple[str, list[str]]] = []
    path_stack: list[str] = []
    current_heading = ""
    buffer: list[str] = []

    for line in lines:
        match = _HEADING.match(line)
        if match:
            if buffer:
                sections.append((current_heading, buffer))
                buffer = []
            level, title = len(match.group(1)), match.group(2).strip()
            path_stack = path_stack[: level - 1]
            path_stack.append(title)
            current_heading = " > ".join(path_stack)
        else:
            buffer.append(line)
    if buffer:
        sections.append((current_heading, buffer))

    chunks: list[Chunk] = []
    for heading, body_lines in sections:
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        for piece in _split_long(body, max_tokens, overlap_tokens):
            chunks.append(
                Chunk(
                    source_type="doc",
                    source_id=doc_id,
                    content=piece,
                    section=heading or None,
                    metadata={**metadata, "source_hash": source_hash, "path": str(path.name)},
                )
            )
    return chunks


# ------------------------------------------------------------------- python --


def _node_lines(node: ast.AST) -> tuple[int, int]:
    """1-based inclusive line range of a node, including its decorators."""
    start = node.lineno
    for decorator in getattr(node, "decorator_list", []):
        start = min(start, decorator.lineno)
    return start, node.end_lineno or node.lineno


def chunk_python(path: Path, *, class_split_lines: int = 150) -> list[Chunk]:
    """Split a Python file into one chunk per top-level function or class.

    Methods stay inside their class unless the class is long, in which case it
    splits per method. Module-level code and the module docstring become one
    chunk so that constants and imports remain findable.
    """
    source = path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    tree = ast.parse(source)
    source_hash = file_hash(source)
    rel = path.name

    def slice_lines(start: int, end: int) -> str:
        return "\n".join(source_lines[start - 1 : end])

    chunks: list[Chunk] = []
    definition_spans: list[tuple[int, int]] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            start, end = _node_lines(node)
            definition_spans.append((start, end))
            if (end - start + 1) > class_split_lines:
                # Long class: one chunk per method, so a hit points at the
                # method rather than at 300 lines of unrelated code.
                for child in node.body:
                    if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                        c_start, c_end = _node_lines(child)
                        chunks.append(
                            Chunk(
                                source_type="code",
                                source_id=rel,
                                content=slice_lines(c_start, c_end),
                                section=f"{node.name}.{child.name}",
                                start_line=c_start,
                                end_line=c_end,
                                metadata={"source_hash": source_hash, "kind": "method"},
                            )
                        )
            else:
                chunks.append(
                    Chunk(
                        source_type="code",
                        source_id=rel,
                        content=slice_lines(start, end),
                        section=node.name,
                        start_line=start,
                        end_line=end,
                        metadata={"source_hash": source_hash, "kind": "class"},
                    )
                )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            start, end = _node_lines(node)
            definition_spans.append((start, end))
            chunks.append(
                Chunk(
                    source_type="code",
                    source_id=rel,
                    content=slice_lines(start, end),
                    section=node.name,
                    start_line=start,
                    end_line=end,
                    metadata={"source_hash": source_hash, "kind": "function"},
                )
            )

    # Whatever is not inside a definition: docstring, imports, constants.
    covered = set()
    for start, end in definition_spans:
        covered.update(range(start, end + 1))
    module_lines = [i for i in range(1, len(source_lines) + 1) if i not in covered]
    module_body = "\n".join(source_lines[i - 1] for i in module_lines).strip()
    if module_body:
        chunks.insert(
            0,
            Chunk(
                source_type="code",
                source_id=rel,
                content=module_body,
                section="module",
                start_line=module_lines[0],
                end_line=module_lines[-1],
                metadata={"source_hash": source_hash, "kind": "module"},
            ),
        )
    return chunks


# ---------------------------------------------------------------------- sql --


def chunk_sql(path: Path) -> list[Chunk]:
    """Split a SQL file per statement, naming each from its `-- name:` comment.

    Line numbers come from locating each statement's leading comment in the
    source, because sqlglot does not preserve them through a round trip.
    """
    source = path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    source_hash = file_hash(source)
    rel = path.name

    # Anchor on the name comments: each one starts a named query that runs to
    # the line before the next name comment.
    anchors: list[tuple[int, str]] = []
    for index, line in enumerate(source_lines, start=1):
        match = _SQL_NAME.match(line.strip())
        if match:
            anchors.append((index, match.group(1)))

    chunks: list[Chunk] = []
    for position, (start_line, name) in enumerate(anchors):
        end_line = (
            anchors[position + 1][0] - 1 if position + 1 < len(anchors) else len(source_lines)
        )
        body = "\n".join(source_lines[start_line - 1 : end_line]).strip()
        if not body:
            continue
        try:
            sqlglot.parse_one(
                "\n".join(line for line in body.splitlines() if not line.strip().startswith("--")),
                dialect="postgres",
            )
            valid = True
        except Exception:  # noqa: BLE001 - an unparseable query is still worth indexing
            valid = False
        chunks.append(
            Chunk(
                source_type="code",
                source_id=rel,
                content=body,
                section=name,
                start_line=start_line,
                end_line=end_line,
                metadata={"source_hash": source_hash, "kind": "query", "parses": valid},
            )
        )
    return chunks


def chunk_file(path: Path, **kwargs: Any) -> list[Chunk]:
    """Dispatch to the right chunker for a path's suffix."""
    if path.suffix == ".md":
        return chunk_markdown(path, **kwargs)
    if path.suffix == ".py":
        return chunk_python(path, **{k: v for k, v in kwargs.items() if k == "class_split_lines"})
    if path.suffix == ".sql":
        return chunk_sql(path)
    raise ValueError(f"no chunker for {path.suffix}")
