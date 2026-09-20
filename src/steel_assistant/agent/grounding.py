"""Check that the numbers in an answer actually came from the tool outputs.

A model that has just been handed a result table will still occasionally round
wrongly, transpose digits, or restate a figure it inferred rather than read.
This extracts every number from the answer and looks for it in what the tools
returned. It does not prove the answer is right, but an ungrounded number is
always worth flagging, and the share of grounded numbers is a metric the
evaluation reports.

French formatting is the awkward part. The same quantity can appear as
`1 234,5` in the answer and `1234.5` in a result row, and the space may be a
normal space, a non-breaking space or a narrow non-breaking space. Everything
is normalised to a float before comparison.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Thousands separators seen in French text, including the narrow no-break space
# that most French typography actually uses.
_SEPARATORS = "    "

# A number, with optional sign, optional thousands separators, and a decimal
# part introduced by either a comma or a dot.
_NUMBER = re.compile(
    r"[-+]?\d{1,3}(?:[" + _SEPARATORS + r"]\d{3})+(?:[.,]\d+)?"  # grouped
    r"|[-+]?\d+(?:[.,]\d+)?"  # plain
)

# Numbers that carry no factual weight: years, list markers, section numbers.
# Grounding them produces noise, not signal.
_TRIVIAL = frozenset({0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 100.0})

DEFAULT_TOLERANCE = 0.01


@dataclass(slots=True)
class GroundingResult:
    """Outcome of checking one answer."""

    numbers_checked: int = 0
    numbers_grounded: int = 0
    ungrounded: list[str] = field(default_factory=list)

    @property
    def ratio(self) -> float:
        """Share of checked numbers that were found. 1.0 when none were checked."""
        if self.numbers_checked == 0:
            return 1.0
        return self.numbers_grounded / self.numbers_checked

    @property
    def fully_grounded(self) -> bool:
        """True when every checked number was found in the tool outputs."""
        return self.numbers_checked == self.numbers_grounded


def normalise_number(raw: str) -> float | None:
    """Turn a rendered number into a float.

    Handles `1 234,5`, `1 234.5`, `1234.5` and `1,5`. The ambiguous case is
    a lone comma: `1,5` is French for one-and-a-half, while `1,500` is English
    for fifteen hundred. A comma followed by exactly three digits and nothing
    else is read as a thousands separator.
    """
    text = raw.strip()
    for separator in _SEPARATORS:
        text = text.replace(separator, "")
    if not text:
        return None

    if "," in text and "." in text:
        # Both present: the last one is the decimal separator.
        text = (
            text.replace(",", "")
            if text.rindex(".") > text.rindex(",")
            else text.replace(".", "").replace(",", ".")
        )
    elif "," in text:
        integer, _, fraction = text.partition(",")
        text = f"{integer}{fraction}" if len(fraction) == 3 else f"{integer}.{fraction}"

    try:
        return float(text)
    except ValueError:
        return None


def extract_numbers(text: str) -> list[tuple[str, float]]:
    """Every number in a piece of text, as (as written, value)."""
    found = []
    for match in _NUMBER.finditer(text):
        value = normalise_number(match.group())
        if value is not None:
            found.append((match.group(), value))
    return found


def _matches(value: float, candidate: float, tolerance: float) -> bool:
    """True when two numbers agree within a relative tolerance.

    Relative, not absolute, because an answer may reasonably round 959636.7 to
    959637 or to 959636.70 — and because a fixed epsilon that suits kWh totals
    would be far too loose for a severity of 3.
    """
    if candidate == value:
        return True
    scale = max(abs(value), abs(candidate), 1e-9)
    if abs(candidate - value) / scale <= tolerance:
        return True
    # An answer that rounds to the nearest whole number is still grounded.
    return round(candidate) == round(value) and abs(candidate - value) < 1.0


def check_grounding(
    answer: str,
    tool_outputs: list[str],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    skip_trivial: bool = True,
) -> GroundingResult:
    """Check each number in the answer against the tool outputs.

    Args:
        answer: the text shown to the user.
        tool_outputs: rendered SQL tables, document sections and code spans.
        tolerance: relative tolerance for a match.
        skip_trivial: ignore small integers and years, which are usually
            list markers or section numbers rather than claims.

    Returns:
        How many numbers were checked, how many were found, and which were not.
    """
    source = "\n".join(tool_outputs)
    available = [value for _, value in extract_numbers(source)]

    result = GroundingResult()
    for written, value in extract_numbers(answer):
        if skip_trivial and (value in _TRIVIAL or (1900 <= value <= 2100 and value.is_integer())):
            continue
        result.numbers_checked += 1
        if any(_matches(value, candidate, tolerance) for candidate in available):
            result.numbers_grounded += 1
        else:
            result.ungrounded.append(written)
    return result
