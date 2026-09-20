"""Hybrid search against a live index.

Plan section 9.4 asks for three known queries returning the expected source.
These use twelve, covering both corpora and both languages, because retrieval
regressions are quiet: nothing errors, the answers just get worse.
"""

import os

import pytest

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def search():
    from steel_assistant.retrieval.search import hybrid_search

    if not os.environ.get("APP_RW_PASSWORD"):
        pytest.skip("APP_RW_PASSWORD not set")
    try:
        if not hybrid_search("test", "doc", k=1):
            pytest.skip("index is empty; run scripts/build_index.py")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"retrieval unavailable: {exc}")
    return hybrid_search


DOC_CASES = [
    ("défaut Z_Scratch actions immédiates", "PROC-FLT-ZSCR"),
    ("procédure pour les rayures en K", "PROC-FLT-KSCR"),
    ("seuil d'alerte de pointe de consommation", "POL-ENR-PEAK"),
    ("barème des durées de mise en attente qualité", "POL-QUA-HOLD"),
    ("définition du TRS et de ses composantes", "REF-KPI"),
    ("manuel d'exploitation du laminage à froid", "MAN-L2"),
]

CODE_CASES = [
    ("energy intensity formula", "kpi_energy.py"),
    ("how is MTTR computed", "downtime_analysis.py"),
    ("which function decides if a plate goes on hold", "quality_hold.py"),
    ("power factor threshold check", "reactive_power_report.py"),
    ("night shift imputation across midnight", "utils_dates.py"),
    ("named SQL query for downtime by fault", "fault_stats.sql"),
]


@pytest.mark.parametrize(("query", "expected"), DOC_CASES, ids=[e for _, e in DOC_CASES])
def test_document_retrieval(search, query, expected):
    hits = search(query, "doc", k=5)
    assert hits, query
    assert any(hit.source_id == expected for hit in hits), (
        f"{expected} not in top 5: {[h.source_id for h in hits]}"
    )


@pytest.mark.parametrize(("query", "expected"), CODE_CASES, ids=[e for _, e in CODE_CASES])
def test_code_retrieval(search, query, expected):
    hits = search(query, "code", k=5)
    assert hits, query
    assert any(hit.source_id == expected for hit in hits), (
        f"{expected} not in top 5: {[h.source_id for h in hits]}"
    )


def test_keyword_branch_actually_contributes(search):
    """Guards the regression where hybrid was silently identical to dense.

    websearch_to_tsquery ANDs its terms, so before the OR rewrite this query
    matched zero chunks and the keyword branch was dead weight.
    """
    hits = search("défaut Z_Scratch actions immédiates", "doc", k=5, mode="hybrid")
    assert any(hit.keyword_rank is not None for hit in hits), (
        "no hit came from the keyword branch; hybrid has degraded to dense"
    )


def test_hybrid_and_dense_differ(search):
    """If the two modes always agree, the C1-vs-C2 comparison is meaningless."""
    query = "procédure pour les rayures en K"
    hybrid = [h.chunk_id for h in search(query, "doc", k=5, mode="hybrid")]
    dense = [h.chunk_id for h in search(query, "doc", k=5, mode="dense")]
    assert hybrid != dense


def test_metadata_filter_restricts_results(search):
    hits = search("mise en attente qualité", "doc", k=5, filters={"doc_type": "procedure"})
    assert hits
    assert all(hit.metadata.get("doc_type") == "procedure" for hit in hits)


def test_code_citations_carry_exact_line_ranges(search):
    hits = search("energy intensity formula", "code", k=3)
    top = hits[0]
    assert top.start_line is not None and top.end_line >= top.start_line
    assert top.citation() == f"{top.source_id}:L{top.start_line}-L{top.end_line}"
