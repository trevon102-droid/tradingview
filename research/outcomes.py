"""Forward outcomes for events: what price did AFTER the signal was known.

Entry = close of the event bar, at time T = bar_open + bar_seconds. For each horizon H the path is
the bars whose open is in [T, T+H). The finest resolution that fully covers the window is used
(1m, then 5m, then 1h); a horizon shorter than the resolution is unavailable rather than guessed.
A window that is missing >20% of its bars (halts, weekends, data gaps) or touches a bar with a
degraded price (contract-roll contamination) is unavailable too, and counted as excluded.

Everything is computed for a LONG position; `sign` (+1 long / -1 short) turns it into the event's
direction, and the opposite direction is just the negation, reported explicitly by the study.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

HORIZONS_MIN = (5, 15, 30, 60, 240)
MIN_COVERAGE = 0.8
FAVORABLE_ATR = 0.5  # "time to favorable/adverse move" = first time the excursion reaches 0.5 ATR


@dataclass
class Series:
    res: int                # bar seconds
    t: np.ndarray           # bar open, unix seconds
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    bad: np.ndarray         # price_bad flag

    @classmethod
    def from_df(cls, df: pd.DataFrame, res: int) -> "Series":
        bad = df["price_bad"].to_numpy() if "price_bad" in df else np.zeros(len(df), bool)
        return cls(res, (df.index.as_unit("ns").asi8 // 10**9).astype(np.int64), df["high"].to_numpy(float),
                   df["low"].to_numpy(float), df["close"].to_numpy(float), bad)


def _window(s: Series, T: int, H: int):
    """Index range [i, j) of bars with open in [T, T+H), or None if the horizon can't be measured."""
    if H < s.res or H % s.res:
        return None
    i = int(np.searchsorted(s.t, T, side="left"))
    j = int(np.searchsorted(s.t, T + H, side="left"))
    need = max(1, int(np.ceil(MIN_COVERAGE * H / s.res)))
    if j - i < need:
        return None
    if s.t[j - 1] < T + H - 2 * s.res:  # path ends early: the horizon's closing price isn't observed
        return None
    return i, j


def outcome(series: list[Series], T: int, entry: float, H: int, atr: float) -> dict:
    """Long-side forward stats for one horizon (seconds). `series` finest first."""
    for s in series:
        if not len(s.t) or T < s.t[0] or T + H > s.t[-1] + s.res:
            continue
        w = _window(s, T, H)
        if w is None:
            continue
        i, j = w
        if s.bad[i:j].any():
            return {"status": "degraded_price", "res": s.res}
        hi, lo = s.high[i:j], s.low[i:j]
        fwd = s.close[j - 1] - entry
        run_hi = np.maximum.accumulate(hi) - entry
        run_lo = entry - np.minimum.accumulate(lo)
        thr = FAVORABLE_ATR * atr if atr and atr > 0 else np.nan
        up_hit = np.nonzero(run_hi >= thr)[0]
        dn_hit = np.nonzero(run_lo >= thr)[0]
        return {
            "status": "ok", "res": s.res, "bars": j - i,
            "fwd_pts": float(fwd), "fwd_pct": float(fwd / entry * 100),
            "mfe_pts": float(max(run_hi[-1], 0.0)), "mae_pts": float(max(run_lo[-1], 0.0)),
            # minutes from signal to the bar END where the 0.5 ATR excursion is first seen
            "t_up_min": float((s.t[i + up_hit[0]] + s.res - T) / 60) if len(up_hit) else None,
            "t_dn_min": float((s.t[i + dn_hit[0]] + s.res - T) / 60) if len(dn_hit) else None,
        }
    return {"status": "unavailable"}


def outcomes_for(events: list[dict], series: list[Series], horizons=HORIZONS_MIN) -> pd.DataFrame:
    """One row per (event_id, horizon). Long-side numbers; study applies the direction sign."""
    rows = []
    for e in events:
        T = e["bar_open"] + _tf_seconds(e["timeframe"])
        atr = e["context"].get("atr") or np.nan
        for h in horizons:
            o = outcome(series, T, e["price"], h * 60, atr)
            rows.append({"event_id": e["event_id"], "horizon": h, "atr": atr, "session": e.get("session"), **o})
    return pd.DataFrame(rows)


def _tf_seconds(tf: str) -> int:
    return {"1m": 60, "5m": 300, "1h": 3600}[tf]
