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


def _bars(start_et: str, end_et: str, freq="5min", price=100.0):
    idx = pd.date_range(pd.Timestamp(start_et, tz=ET), pd.Timestamp(end_et, tz=ET), freq=freq, inclusive="left")
    n = len(idx)
    import numpy as np
    close = price + np.arange(n) * 0.25
    return pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5, "close": close,
                         "volume": np.full(n, 10.0)}, index=idx.tz_convert("UTC"))


def test_rth_vwap_resets_at_open_and_freezes_after_close():
    from ofcore.indicators import rth_vwap
    df = _bars("2026-10-05 18:00", "2026-10-07 17:00")
    rv = rth_vwap(df, 300)
    et_idx = df.index.tz_convert(ET)
    first_rth = (et_idx.strftime("%H:%M") == "09:30") & (et_idx.day == 6)
    tp = (df.high + df.low + df.close) / 3
    assert rv["vwap"][first_rth].iloc[0] == pytest.approx(tp[first_rth].iloc[0])      # reset at 09:30
    assert rv["vwap"][(et_idx.day == 6) & (et_idx.hour < 9)].isna().all()             # no RTH yet
    close_val = rv["vwap"][(et_idx.day == 6) & (et_idx.strftime("%H:%M") == "15:55")].iloc[0]
    after = rv["vwap"][(et_idx.day == 6) & (et_idx.hour >= 16) | (et_idx.day == 7) & (et_idx.hour < 9)]
    assert (after == close_val).all()                                                  # frozen overnight
    second_open = (et_idx.day == 7) & (et_idx.strftime("%H:%M") == "09:30")
    assert rv["vwap"][second_open].iloc[0] == pytest.approx(tp[second_open].iloc[0])  # next day resets
    assert rv["in_rth"].sum() == 2 * 78                                                # 6.5h of 5m bars x 2


def test_rth_vwap_across_dst_change():
    from ofcore.indicators import rth_vwap
    df = _bars("2026-10-30 08:00", "2026-11-02 17:00")
    rv = rth_vwap(df, 300)
    et_idx = df.index.tz_convert(ET)
    rth_et = et_idx[rv["in_rth"].to_numpy()]
    for d in (30, 2):  # Friday on EDT, Monday on EST: both 09:30-16:00 local
        hours = rth_et[rth_et.day == d]
        assert hours.min().strftime("%H:%M") == "09:30" and hours.max().strftime("%H:%M") == "15:55"


def test_rth_vwap_is_point_in_time():
    """Adding later bars must not change any earlier RTH VWAP value."""
    from ofcore.indicators import rth_vwap
    df = _bars("2026-10-05 18:00", "2026-10-07 17:00")
    full = rth_vwap(df, 300)["vwap"]
    for cut in (150, 230, 300, 400):
        part = rth_vwap(df.iloc[:cut], 300)["vwap"]
        pd.testing.assert_series_equal(part, full.iloc[:cut])
