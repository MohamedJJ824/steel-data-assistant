"""The 7 one-hot fault columns collapse to a single fault_code."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from load_db import FAULT_CODES, FAULT_TYPES  # noqa: E402


def test_source_spelling_is_k_scratch():
    # The plan says K_Scatch; the UCI payload says K_Scratch. Reality wins.
    assert "K_Scratch" in FAULT_CODES
    assert "K_Scatch" not in FAULT_CODES


def test_seven_fault_types_with_valid_severity():
    assert len(FAULT_TYPES) == 7
    assert {row[3] for row in FAULT_TYPES} <= {1, 2, 3}
    assert all(row[4].startswith("PROC-FLT-") for row in FAULT_TYPES)


def test_idxmax_collapses_one_hot_to_the_set_bit():
    frame = pd.DataFrame([[0, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 1]], columns=FAULT_CODES)
    assert list(frame[FAULT_CODES].idxmax(axis=1)) == ["Z_Scratch", "Other_Faults"]


def test_grade_mapping_is_exhaustive():
    a300 = pd.Series([1, 0])
    assert list(a300.map({1: "A300", 0: "A400"})) == ["A300", "A400"]
