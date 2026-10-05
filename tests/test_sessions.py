"""Shared session logic: RTH / ETH / CME session boundaries, DST, Sunday open, holidays."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from ofcore import sessions as S

ET = ZoneInfo("America/New_York")


def et(*a) -> float:
    return datetime(*a, tzinfo=ET).timestamp()


@pytest.mark.parametrize("ts,label", [
    (et(2026, 10, 6, 9, 29, 59), "ETH"),
    (et(2026, 10, 6, 9, 30), "RTH"),           # RTH open
    (et(2026, 10, 6, 15, 59, 59), "RTH"),
    (et(2026, 10, 6, 16, 0), "ETH"),           # RTH close
    (et(2026, 10, 6, 17, 30), "CLOSED"),       # daily halt
    (et(2026, 10, 6, 18, 0), "ETH"),           # Globex reopen
    (et(2026, 10, 7, 2, 0), "ETH"),            # overnight
    (et(2026, 10, 3, 12, 0), "CLOSED"),        # Saturday
    (et(2026, 10, 4, 17, 59), "CLOSED"),       # Sunday before open
    (et(2026, 10, 4, 18, 0), "ETH"),           # Sunday open
    (et(2026, 10, 9, 17, 0), "CLOSED"),        # Friday close
])
def test_session_labels(ts, label):
    assert S.session_label(ts) == label


def test_rth_is_wall_clock_across_dst():
    # 09:30 ET is 13:30 UTC in summer (EDT) and 14:30 UTC in winter (EST)
    summer, winter = S.rth_bounds(date(2026, 10, 30)), S.rth_bounds(date(2026, 11, 2))
    assert datetime.fromtimestamp(summer[0], ZoneInfo("UTC")).hour == 13
    assert datetime.fromtimestamp(winter[0], ZoneInfo("UTC")).hour == 14
    assert summer[1] - summer[0] == winter[1] - winter[0] == 6.5 * 3600
    # spring forward 2027-03-14: Monday RTH still 09:30-16:00 local
    b = S.rth_bounds(date(2027, 3, 15))
    assert datetime.fromtimestamp(b[0], ET).strftime("%H:%M") == "09:30"


def test_cme_session_sunday_monday_and_dst():
    assert S.cme_session_of(et(2026, 10, 4, 18, 0)) == date(2026, 10, 5)   # Sunday open -> Monday session
    assert S.cme_session_of(et(2026, 10, 5, 16, 59)) == date(2026, 10, 5)
    assert S.cme_session_of(et(2026, 10, 5, 17, 0)) == date(2026, 10, 6)
    start, end = S.cme_session_bounds(date(2026, 11, 2))                   # spans the Nov 1 DST change
    assert end - start == 25 * 3600 or end - start == 24 * 3600


def test_holidays_and_early_closes():
    assert S.rth_bounds(date(2026, 11, 26)) is None            # Thanksgiving
    assert S.rth_bounds(date(2026, 4, 3)) is None              # Good Friday 2026
    assert S.rth_bounds(date(2026, 7, 3)) is None              # Jul 4 is Saturday -> observed Friday
    assert S.rth_bounds(date(2026, 6, 19)) is None             # Juneteenth
    o, c = S.rth_bounds(date(2026, 11, 27))                     # day after Thanksgiving: 13:00 close
    assert datetime.fromtimestamp(c, ET).strftime("%H:%M") == "13:00"
    assert S.session_label(et(2026, 11, 27, 13, 30)) == "ETH"
    assert S.session_label(et(2026, 11, 26, 11, 0)) == "ETH"   # holiday: no RTH
    assert date(2027, 1, 1) in S.nyse_holidays(2027) and date(2027, 12, 31) not in S.nyse_holidays(2027)


def test_vectorized_matches_scalar():
    idx = pd.date_range("2026-10-30 00:00", "2026-11-03 23:55", freq="5min", tz="UTC")
    vec = S.cme_session_index(idx)
    for t, d in list(zip(idx, vec))[::37]:
        assert S.cme_session_of(t.timestamp()) == d.date()
    lab = S.bar_labels(idx, 300)
    for t, l_ in list(zip(idx, lab))[::41]:
        assert S.session_label(t.timestamp() + 299) == l_


def test_bar_label_uses_bar_close():
    idx = pd.DatetimeIndex([pd.Timestamp("2026-10-06 09:25", tz=ET).tz_convert("UTC"),
                            pd.Timestamp("2026-10-06 09:30", tz=ET).tz_convert("UTC"),
                            pd.Timestamp("2026-10-06 15:55", tz=ET).tz_convert("UTC"),
                            pd.Timestamp("2026-10-06 16:00", tz=ET).tz_convert("UTC")])
    assert list(S.bar_labels(idx, 300)) == ["ETH", "RTH", "RTH", "ETH"]
