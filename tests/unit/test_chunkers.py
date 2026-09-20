"""Chunker tests.

Line ranges are a graded output: an answer cites `kpi_energy.py:L12-L38`, so a
range that is off by one is a wrong citation. These assert exact values.
"""

from pathlib import Path

import pytest

from steel_assistant.retrieval.chunkers import (
    Chunk,
    chunk_file,
    chunk_markdown,
    chunk_python,
    chunk_sql,
    file_hash,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CORPUS = Path(__file__).resolve().parents[2] / "corpus" / "legacy_code"


# ------------------------------------------------------------------ python --


@pytest.fixture(scope="module")
def py_chunks() -> list[Chunk]:
    return chunk_python(FIXTURES / "sample_module.py")


def test_every_top_level_symbol_becomes_a_chunk(py_chunks):
    sections = [c.section for c in py_chunks]
    assert sections == [
        "module",
        "first_function",
        "decorated_function",
        "SmallClass",
        "last_function",
    ]


def test_module_chunk_holds_imports_and_constants(py_chunks):
    module = py_chunks[0]
    assert module.section == "module"
    assert "THRESHOLD = 10.0" in module.content
    assert "import math" in module.content
    # The docstring belongs to the module chunk too.
    assert "Fixture module docstring" in module.content


def test_exact_line_ranges(py_chunks):
    by_section = {c.section: (c.start_line, c.end_line) for c in py_chunks}
    assert by_section["first_function"] == (8, 10)
    assert by_section["SmallClass"] == (19, 26)
    assert by_section["last_function"] == (29, 31)


def test_decorator_is_included_in_the_range(py_chunks):
    start, end = next(
        (c.start_line, c.end_line) for c in py_chunks if c.section == "decorated_function"
    )
    source = (FIXTURES / "sample_module.py").read_text().splitlines()
    assert source[start - 1].strip() == "@staticmethod"
    assert (start, end) == (13, 16)


def test_line_ranges_round_trip_to_the_real_source(py_chunks):
    """Slicing the file by a chunk's range must reproduce that chunk exactly."""
    source = (FIXTURES / "sample_module.py").read_text().splitlines()
    for chunk in py_chunks:
        if chunk.section == "module":
            continue  # non-contiguous by construction
        sliced = "\n".join(source[chunk.start_line - 1 : chunk.end_line])
        assert sliced == chunk.content, chunk.section


def test_short_class_is_not_split_per_method(py_chunks):
    sections = [c.section for c in py_chunks]
    assert "SmallClass" in sections
    assert "SmallClass.method_a" not in sections


def test_long_class_splits_per_method(tmp_path):
    body = "\n".join(f"        x = {i}" for i in range(60))
    source = f"class Big:\n    def one(self):\n{body}\n\n    def two(self):\n{body}\n"
    path = tmp_path / "big.py"
    path.write_text(source)
    chunks = chunk_python(path, class_split_lines=10)
    assert [c.section for c in chunks if c.section != "module"] == ["Big.one", "Big.two"]


def test_embed_text_prepends_file_and_symbol(py_chunks):
    chunk = next(c for c in py_chunks if c.section == "first_function")
    text = chunk.embed_text()
    assert text.startswith("File: sample_module.py\nSymbol: first_function")


# ---------------------------------------------------------------- markdown --


@pytest.fixture(scope="module")
def md_chunks() -> list[Chunk]:
    return chunk_markdown(FIXTURES / "sample_doc.md")


def test_heading_path_is_nested(md_chunks):
    sections = [c.section for c in md_chunks]
    assert "Titre principal" in sections
    assert "Titre principal > Actions immédiates" in sections
    assert "Titre principal > Actions immédiates > Sous-section" in sections
    assert "Titre principal > Escalade" in sections


def test_sibling_heading_pops_the_stack(md_chunks):
    """Escalade is a sibling of Actions immédiates, not a child of Sous-section."""
    assert "Titre principal > Escalade" in [c.section for c in md_chunks]
    assert not any(c.section and c.section.endswith("Sous-section > Escalade") for c in md_chunks)


def test_front_matter_becomes_metadata(md_chunks):
    chunk = md_chunks[0]
    assert chunk.source_id == "TEST-DOC"
    assert chunk.metadata["fault_code"] == "Z_Scratch"
    assert chunk.metadata["doc_type"] == "procedure"


def test_front_matter_is_not_in_the_content(md_chunks):
    for chunk in md_chunks:
        assert "doc_id:" not in chunk.content
        assert "---" not in chunk.content


def test_embed_text_prepends_title_and_section(md_chunks):
    chunk = next(c for c in md_chunks if c.section == "Titre principal > Escalade")
    assert chunk.embed_text().startswith("Titre de test > Titre principal > Escalade")


# --------------------------------------------------------------------- sql --


def test_sql_splits_on_name_comments():
    chunks = chunk_sql(CORPUS / "fault_stats.sql")
    assert [c.section for c in chunks] == [
        "fault_counts_by_line",
        "monthly_fault_trend",
        "downtime_by_fault",
        "peak_energy_intervals",
        "energy_by_load_type",
        "plates_on_hold",
    ]


def test_sql_chunks_parse_and_have_ranges():
    chunks = chunk_sql(CORPUS / "fault_stats.sql")
    for chunk in chunks:
        assert chunk.metadata["parses"] is True, chunk.section
        assert chunk.start_line < chunk.end_line
        assert chunk.source_type == "code"


def test_sql_ranges_do_not_overlap():
    chunks = chunk_sql(CORPUS / "fault_stats.sql")
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        assert earlier.end_line < later.start_line


# ------------------------------------------------------------------- misc --


def test_file_hash_is_stable_and_content_sensitive():
    assert file_hash("abc") == file_hash("abc")
    assert file_hash("abc") != file_hash("abd")


def test_dispatch_by_suffix():
    assert chunk_file(FIXTURES / "sample_doc.md")[0].source_type == "doc"
    assert chunk_file(FIXTURES / "sample_module.py")[0].source_type == "code"
    with pytest.raises(ValueError, match="no chunker"):
        chunk_file(Path("x.txt"))


def test_every_corpus_file_chunks_without_error():
    paths = sorted(CORPUS.glob("*.py")) + sorted(CORPUS.glob("*.sql"))
    assert len(paths) == 12
    for path in paths:
        chunks = chunk_file(path)
        assert chunks, path.name
        for chunk in chunks:
            assert chunk.content.strip()
            assert chunk.start_line is not None
