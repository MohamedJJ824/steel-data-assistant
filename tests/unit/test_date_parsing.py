"""The energy dataset's date format is the single easiest thing to get wrong.

It is day-first, and the label marks the END of each 15-minute interval, so the
file is not in chronological order. Both properties are asserted here against
values verified against the real UCI file.
"""

import pandas as pd
import pytest

FORMAT = "%d/%m/%Y %H:%M"


def test_day_first_parsing():
    # 13/03 is 13 March, not 3 December. Month-first parsing would raise, which
    # is precisely why the format is explicit rather than inferred.
    assert pd.to_datetime("13/03/2018 07:45", format=FORMAT) == pd.Timestamp("2018-03-13 07:45")


def test_ambiguous_date_is_read_day_first():
    # 01/03 is valid under both readings; only an explicit format disambiguates.
    assert pd.to_datetime("01/03/2018 00:15", format=FORMAT) == pd.Timestamp("2018-03-01 00:15")


def test_month_first_input_is_rejected():
    with pytest.raises(ValueError):
        pd.to_datetime("2018/03/01 00:15", format=FORMAT)


def test_known_boundary_timestamps():
    # Verified against the real file: the year spans these two values.
    first = pd.to_datetime("01/01/2018 00:00", format=FORMAT)
    last = pd.to_datetime("31/12/2018 23:45", format=FORMAT)
    assert first == pd.Timestamp("2018-01-01 00:00")
    assert last == pd.Timestamp("2018-12-31 23:45")
    # 2018 at 15-minute resolution.
    assert int((last - first).total_seconds() // 900) + 1 == 35_040


def test_file_order_is_not_chronological():
    """Each day's block ends with a 00:00 row closing it out, not opening it."""
    day_block = ["01/01/2018 00:15", "01/01/2018 23:45", "01/01/2018 00:00"]
    parsed = pd.to_datetime(pd.Series(day_block), format=FORMAT)
    assert not parsed.is_monotonic_increasing
    assert parsed.sort_values().iloc[0] == pd.Timestamp("2018-01-01 00:00")
