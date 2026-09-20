"""Number grounding, with the French formatting the plan calls out."""

import pytest

from steel_assistant.agent.grounding import (
    check_grounding,
    extract_numbers,
    normalise_number,
)

# --------------------------------------------------------------- normalise --


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234", 1234.0),
        ("1234.5", 1234.5),
        ("1 234,5", 1234.5),  # normal space
        ("1 234,5", 1234.5),  # non-breaking space
        ("1 234,5", 1234.5),  # narrow non-breaking space
        ("959 636,7", 959636.7),
        ("12,3", 12.3),
        ("-5,5", -5.5),
        ("+7", 7.0),
        ("0,000512", 0.000512),
        ("1,234.5", 1234.5),  # English: comma groups, dot decimal
        ("1.234,5", 1234.5),  # German/French: dot groups, comma decimal
    ],
)
def test_normalise(raw, expected):
    assert normalise_number(raw) == pytest.approx(expected)


def test_lone_comma_with_three_digits_is_a_thousands_separator():
    """`1,500` is fifteen hundred; `1,50` is one and a half."""
    assert normalise_number("1,500") == pytest.approx(1500.0)
    assert normalise_number("1,50") == pytest.approx(1.50)


def test_garbage_returns_none():
    assert normalise_number("") is None
    assert normalise_number("abc") is None


# ----------------------------------------------------------------- extract --


def test_extract_from_french_prose():
    found = extract_numbers("La consommation atteint 959 636,7 kWh soit 12,3 % de plus.")
    assert [value for _, value in found] == pytest.approx([959636.7, 12.3])


def test_extract_preserves_the_written_form():
    written, value = extract_numbers("seuil de 1 234,5 kWh")[0]
    assert written == "1 234,5"
    assert value == pytest.approx(1234.5)


def test_percentage_sign_is_not_part_of_the_number():
    assert [v for _, v in extract_numbers("12,3 %")] == pytest.approx([12.3])


# ---------------------------------------------------------------- grounding --


def test_french_answer_grounded_in_english_formatted_table():
    """The real case: the answer is French, the SQL result is not."""
    result = check_grounding(
        "La consommation totale est de 959 636,7 kWh.",
        ["total_kwh\n---\n959636.7\n(1 rows)"],
    )
    assert result.numbers_checked == 1
    assert result.fully_grounded


def test_invented_number_is_caught():
    result = check_grounding(
        "La consommation totale est de 1 000 000 kWh.",
        ["total_kwh\n---\n959636.7"],
    )
    assert result.numbers_checked == 1
    assert result.numbers_grounded == 0
    assert result.ungrounded == ["1 000 000"]


def test_rounding_is_tolerated():
    result = check_grounding("environ 959 637 kWh", ["959636.7"])
    assert result.fully_grounded


def test_tolerance_is_relative_not_absolute():
    """A 1-unit error is fine on a large total and wrong on a severity."""
    assert check_grounding("959 637", ["959636.7"]).fully_grounded
    assert not check_grounding("la gravité est 7", ["severity\n---\n3"]).fully_grounded


def test_trivial_numbers_are_skipped():
    """List markers and years are not factual claims."""
    result = check_grounding(
        "1. Isoler la tôle. 2. Prévenir le responsable. En 2018, 42 événements.",
        ["count\n---\n42"],
    )
    assert result.numbers_checked == 1
    assert result.fully_grounded


def test_answer_with_no_numbers_is_vacuously_grounded():
    result = check_grounding("La procédure demande d'isoler la tôle.", ["irrelevant"])
    assert result.numbers_checked == 0
    assert result.ratio == 1.0
    assert result.fully_grounded


def test_partial_grounding_ratio():
    result = check_grounding(
        "Il y a 42 événements pour 8 837 minutes et 99 tôles.",
        ["42", "8837"],
    )
    assert result.numbers_checked == 3
    assert result.numbers_grounded == 2
    assert result.ratio == pytest.approx(2 / 3)


def test_grounded_across_several_tool_outputs():
    result = check_grounding(
        "72 heures d'attente, et 8 837 minutes d'arrêt.",
        ["hold hours: 72", "downtime\n---\n8837"],
    )
    assert result.fully_grounded


def test_empty_tool_output_grounds_nothing():
    result = check_grounding("Le total est 42.", [])
    assert result.numbers_checked == 1
    assert result.numbers_grounded == 0
