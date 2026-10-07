"""The one place that knows about sessions, time zones and DST. Everything else imports from here.

    CME session D   17:00 ET on D-1 -> 17:00 ET on D  (Globex trades 18:00-17:00; the 17:00-18:00 halt
                    hour belongs to the session that opens at 18:00). Named by its closing date.
    RTH / NY cash   09:30 -> 16:00 ET on NYSE trading days (13:00 on early-close days).
    ETH             everything in a CME session that isn't RTH.

All boundaries are ET wall-clock times converted with zoneinfo, so DST is handled. Holidays follow the
NYSE cash calendar (rules below), which is what "RTH" means for ES/NQ. CME Globex holiday hours differ
(e.g. early halts), so ETH on holidays is labeled ETH, not CLOSED; that's an approximation.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET_NAME = "America/New_York"
ET = ZoneInfo(ET_NAME)
CME_ROLL = time(17, 0)
CME_OPEN = time(18, 0)
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)

RTH, ETH, CLOSED = "RTH", "ETH", "CLOSED"


# ---------------------------------------------------------------- calendar

def _nth_weekday(y: int, m: int, weekday: int, n: int) -> date:
    d = date(y, m, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(y: int, m: int, weekday: int) -> date:
    d = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _easter(y: int) -> date:  # anonymous Gregorian algorithm
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    return date(y, month, (h + l_ - 7 * m + 114) % 31 + 1)


def _observed(d: date) -> date | None:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def nyse_holidays(y: int) -> frozenset[date]:
    h = {
        _nth_weekday(y, 1, 0, 3),            # MLK
        _nth_weekday(y, 2, 0, 3),            # Presidents
        _easter(y) - timedelta(days=2),      # Good Friday
        _last_weekday(y, 5, 0),              # Memorial
        _observed(date(y, 7, 4)),            # Independence
        _nth_weekday(y, 9, 0, 1),            # Labor
        _nth_weekday(y, 11, 3, 4),           # Thanksgiving
        _observed(date(y, 12, 25)),          # Christmas
    }
    ny = date(y, 1, 1)
    if ny.weekday() != 5:  # NYSE doesn't observe a Saturday New Year on the prior Friday
        h.add(_observed(ny))
    if y >= 2022:
        h.add(_observed(date(y, 6, 19)))     # Juneteenth
    return frozenset(h)


@lru_cache(maxsize=None)
def nyse_early_closes(y: int) -> frozenset[date]:
    out = {_nth_weekday(y, 11, 3, 4) + timedelta(days=1)}          # day after Thanksgiving
    for d in (date(y, 7, 3), date(y, 12, 24)):                       # Jul 3 / Christmas Eve, if a trading day
        if d.weekday() < 5 and d not in nyse_holidays(y):
            out.add(d)
    return frozenset(out)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in nyse_holidays(d.year)


def rth_bounds(d: date) -> tuple[float, float] | None:
    """[open, close) unix seconds of the RTH session on calendar date d, or None if no cash session."""
    if not is_trading_day(d):
        return None
    close = EARLY_CLOSE if d in nyse_early_closes(d.year) else RTH_CLOSE
    return datetime.combine(d, RTH_OPEN, ET).timestamp(), datetime.combine(d, close, ET).timestamp()


# ---------------------------------------------------------------- scalar API

def cme_session_of(ts: float) -> date:
    """CME session (named by closing date) that the instant `ts` belongs to."""
    wall = datetime.fromtimestamp(ts, ET)
    return (wall + timedelta(days=1)).date() if wall.time() >= CME_ROLL else wall.date()


def cme_session_bounds(d: date) -> tuple[float, float]:
    """[start, end) unix seconds of CME session d: 17:00 ET on d-1 to 17:00 ET on d."""
    return (datetime.combine(d - timedelta(days=1), CME_ROLL, ET).timestamp(),
            datetime.combine(d, CME_ROLL, ET).timestamp())


def session_label(ts: float) -> str:
    """RTH / ETH / CLOSED for an instant. CLOSED = weekend gap and the daily 17:00-18:00 ET halt."""
    wall = datetime.fromtimestamp(ts, ET)
    t, wd = wall.time(), wall.weekday()
    if wd == 5 or (wd == 6 and t < CME_OPEN) or (wd == 4 and t >= CME_ROLL) or CME_ROLL <= t < CME_OPEN:
        return CLOSED
    b = rth_bounds(wall.date())
    return RTH if b and b[0] <= ts < b[1] else ETH


def is_rth(ts: float) -> bool:
    return session_label(ts) == RTH


# ---------------------------------------------------------------- vectorized API (pandas UTC index)

def cme_session_index(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """CME session date (naive midnight) per timestamp. Equivalent to cme_session_of, vectorized."""
    wall = idx.tz_convert(ET_NAME).tz_localize(None)
    roll = wall.normalize() + pd.Timedelta(hours=CME_ROLL.hour, minutes=CME_ROLL.minute)
    return wall.normalize() + pd.to_timedelta((wall >= roll).astype(int), unit="D")


def bar_labels(idx: pd.DatetimeIndex, bar_seconds: int) -> np.ndarray:
    """Session label per bar, judged at the bar's last instant (when its close is known).
    A 09:25-09:30 bar is ETH; 09:30-09:35 is RTH; 15:55-16:00 is RTH; 16:00-16:05 is ETH."""
    last = idx.as_unit("ns").asi8 // 10**9 + bar_seconds - 1
    return np.array([session_label(float(t)) for t in last])


def rth_mask(idx: pd.DatetimeIndex, bar_seconds: int) -> np.ndarray:
    return bar_labels(idx, bar_seconds) == RTH


def rth_session_key(idx: pd.DatetimeIndex, bar_seconds: int) -> pd.Series:
    """Calendar date for RTH bars, NaT otherwise (used to anchor RTH VWAP)."""
    lab = bar_labels(idx, bar_seconds)
    d = idx.tz_convert(ET_NAME).tz_localize(None).normalize()
    return pd.Series(np.where(lab == RTH, d, pd.NaT), index=idx, dtype="datetime64[ns]")


def anchor_shift(anchor: time) -> pd.Timedelta:
    """How far to push the ET wall clock so `anchor` lands on midnight."""
    return pd.Timedelta(hours=24 - anchor.hour, minutes=-anchor.minute)


def wall_shifted(idx: pd.DatetimeIndex, anchor: time) -> pd.DatetimeIndex:
    """ET wall clock shifted so `anchor` lands on midnight (for session-aligned bucketing)."""
    return idx.tz_convert(ET_NAME).tz_localize(None) + anchor_shift(anchor)
