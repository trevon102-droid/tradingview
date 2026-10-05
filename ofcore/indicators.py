"""VWAPs, EMAs, RVOL and estimated delta / CVD.

Heads up on delta: Yahoo/CSV bars have no bid/ask split, so delta here is *estimated* from where
each bar closed in its range (close-location volume). It tracks real CVD direction well on
swing timeframes but it is not a footprint. The Pine delta script uses lower-timeframe
intrabars, which is closer to the real thing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .data import ET
from .sessions import cme_session_index, rth_session_key


def is_daily(df: pd.DataFrame) -> bool:
    return len(df) > 1 and pd.Series(df.index).diff().median() >= pd.Timedelta(hours=20)


def trading_day(df: pd.DataFrame) -> pd.Series:
    """Trading date each bar belongs to (Sunday 18:00 ET bar -> Monday)."""
    if is_daily(df):
        return pd.Series(df.index.tz_convert(ET).tz_localize(None).normalize(), index=df.index)
    return pd.Series(cme_session_index(df.index), index=df.index)


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def anchor_key(df: pd.DataFrame, anchor: str) -> pd.Series:
    td = trading_day(df)
    if anchor == "D":
        return td
    return td.dt.to_period({"W": "W-SUN", "M": "M", "Q": "Q"}[anchor]).astype(str)


def anchored_vwap(df: pd.DataFrame, anchor: str = "W") -> pd.DataFrame:
    """VWAP reset each D/W/M/Q with 1σ and 2σ volume-weighted bands."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    v = df["volume"].clip(lower=0)
    v = v.where(v > 0, 1.0) if v.sum() == 0 else v  # FX has no volume -> fall back to TWAP
    key = anchor_key(df, anchor)
    g = pd.DataFrame({"pv": tp * v, "pv2": tp * tp * v, "v": v, "k": key.values}, index=df.index).groupby("k")
    cv = g["v"].cumsum().replace(0, np.nan)
    vwap = g["pv"].cumsum() / cv
    sd = np.sqrt((g["pv2"].cumsum() / cv - vwap**2).clip(lower=0))
    return pd.DataFrame({"vwap": vwap, "u1": vwap + sd, "l1": vwap - sd, "u2": vwap + 2 * sd, "l2": vwap - 2 * sd})


def rvol(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Relative volume. Intraday: vs the same time-of-day over the last n sessions. Daily: vs n-day avg."""
    v = df["volume"].astype(float)
    if is_daily(df):
        base = v.shift(1).rolling(n, min_periods=5).mean()
    else:
        wall = df.index.tz_convert(ET)
        tod = np.asarray(wall.hour * 60 + wall.minute)
        prev = v.groupby(tod).shift(1)
        base = (prev.groupby(tod).rolling(n, min_periods=3).mean()
                .reset_index(level=0, drop=True).reindex(v.index))
    return (v / base.replace(0, np.nan)).rename("rvol")


def est_delta(df: pd.DataFrame) -> pd.Series:
    """Close-location delta: +vol if bar closed on its high, -vol on its low."""
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    clv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng
    return (clv.fillna(0) * df["volume"]).rename("delta")


def cvd(df: pd.DataFrame, reset: str | None = "W") -> pd.Series:
    d = est_delta(df)
    if reset is None:
        return d.cumsum().rename("cvd")
    return d.groupby(anchor_key(df, reset).values).cumsum().rename("cvd")


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def rth_vwap(df: pd.DataFrame, bar_seconds: int) -> pd.DataFrame:
    """RTH VWAP: resets at 09:30 ET, accumulates only on RTH bars, frozen after 16:00 ET.

    Columns: vwap, sd, in_rth. Outside RTH, `vwap`/`sd` carry the most recent RTH session's final
    value forward (already known at that time, so point-in-time safe); before the first RTH bar it's NaN."""
    key = rth_session_key(df.index, bar_seconds)
    in_rth = key.notna()
    tp = (df["high"] + df["low"] + df["close"]) / 3
    v = df["volume"].clip(lower=0).astype(float)
    if v[in_rth].sum() == 0:
        v = pd.Series(1.0, index=df.index)
    sub = pd.DataFrame({"pv": tp * v, "pv2": tp * tp * v, "v": v, "k": key})[in_rth]
    g = sub.groupby("k")
    cv = g["v"].cumsum().replace(0, np.nan)
    vw = g["pv"].cumsum() / cv
    sd = np.sqrt((g["pv2"].cumsum() / cv - vw**2).clip(lower=0))
    out = pd.DataFrame({"vwap": vw, "sd": sd}).reindex(df.index).ffill()
    out["in_rth"] = in_rth.to_numpy()
    return out
