"""Point-in-time replay: walk bars one at a time and record setups exactly as the live scanner would.

At bar i the detector sees ONLY bars [i - window, i]. An event is recorded on the bar where a setup
switches ON (same transition logic as the live scanner). Context is read from causal series (each value
at bar i depends only on bars <= i), which tests/test_research.py checks against truncated recomputation.
Gamma is never available here: there is no historical options chain, so gamma setups can't be replayed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ofcore.auction import auction_read
from ofcore.indicators import anchored_vwap, atr, ema, rth_vwap, rvol
from ofcore.sessions import bar_labels
from ofcore.setups import Thresholds, detect

from .records import EventRecord, check_quality, detector_version, make_id, signal_time

# Pre-set, not tuned: 1h mirrors the live scanner (60-day composite); 5m uses a 10-day composite.
WINDOW_DAYS = {"5m": 10, "1h": 60}
BAR_SECONDS = {"1m": 60, "5m": 300, "1h": 3600}
HIGH_RVOL = 1.5


def causal_context(df: pd.DataFrame, bar_seconds: int) -> pd.DataFrame:
    """Per-bar context columns. Every column is causal: value at i uses bars <= i only."""
    rv = rth_vwap(df, bar_seconds)
    e9, e21, e50 = ema(df["close"], 9), ema(df["close"], 21), ema(df["close"], 50)
    stack = np.where((e9 > e21) & (e21 > e50), "bull", np.where((e9 < e21) & (e21 < e50), "bear", "mixed"))
    return pd.DataFrame({
        "rth_vwap": rv["vwap"], "in_rth": rv["in_rth"],
        "weekly_vwap": anchored_vwap(df, "W")["vwap"], "monthly_vwap": anchored_vwap(df, "M")["vwap"],
        "rvol": rvol(df), "atr": atr(df), "ema_stack": stack,
        "session": bar_labels(df.index, bar_seconds),
    }, index=df.index)


def _r(x) -> float | None:
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 6)


def replay(sym: str, tf: str, df: pd.DataFrame, tick: float, source: str,
           th: Thresholds = Thresholds(), start: int | None = None, end: int | None = None) -> list[EventRecord]:
    """Events for bars [start, end) of df. `df` may carry price_bad/volume_bad quality flags."""
    bar_s = BAR_SECONDS[tf]
    ctx = causal_context(df[["open", "high", "low", "close", "volume"]], bar_s)
    t = df.index.as_unit("ns").asi8
    win = np.int64(WINDOW_DAYS[tf] * 86400 * 10**9)
    first = int(np.searchsorted(t, t[0] + win)) if len(t) else 0
    start = max(first, start or 0)
    end = len(df) if end is None else end
    price_bad = df["price_bad"].to_numpy() if "price_bad" in df else np.zeros(len(df), bool)
    vol_bad = df["volume_bad"].to_numpy() if "volume_bad" in df else np.zeros(len(df), bool)
    det = detector_version()
    ohlcv = df[["open", "high", "low", "close", "volume"]]

    out: list[EventRecord] = []
    prev_codes: set[str] | None = None
    for i in range(max(start - 1, first), end):
        lo = int(np.searchsorted(t, t[i] - win))
        sub = ohlcv.iloc[lo:i + 1]
        a = auction_read(sub, tick)
        sigs = {s.code: s for s in detect(sym, sub, a, None, th)}  # never gamma on history
        if prev_codes is not None and i >= start:
            new = [sigs[c] for c in sigs if c not in prev_codes]
            if new:
                out += [build_record(sym, tf, s, i, df, ctx, a, price_bad, vol_bad, source, det, bar_s) for s in new]
        prev_codes = set(sigs)
    return out


def build_record(sym, tf, s, i, df, ctx, a, price_bad, vol_bad, source, det, bar_s, gamma: dict | None = None) -> EventRecord:
    """One normalized record from what was known at bar i. `gamma` only for LIVE events (never history)."""
    bar_open = int(df.index[i].timestamp())
    c = ctx.iloc[i]
    close, o = float(df["close"].iloc[i]), float(df["open"].iloc[i])
    hypothesis = None
    if s.direction == "info":
        if s.code == "naked_poc":
            hypothesis = "toward_level"   # magnet: price travels to the naked POC
        elif s.code == "rvol":
            hypothesis = "with_bar"       # initiative: the high-RVOL bar's direction continues
    rv = c["rth_vwap"]
    context = {
        "rth_vwap": _r(rv), "weekly_vwap": _r(c["weekly_vwap"]), "monthly_vwap": _r(c["monthly_vwap"]),
        "vs_rth_vwap": None if pd.isna(rv) else ("above" if close > rv else "below"),
        "vs_weekly_vwap": "above" if close > c["weekly_vwap"] else "below",
        "rvol": _r(c["rvol"]), "rvol_bucket": None if pd.isna(c["rvol"]) else ("high" if c["rvol"] >= HIGH_RVOL else "low"),
        "atr": _r(c["atr"]), "ema_stack": str(c["ema_stack"]),
        "auction_state": a["state"], "auction_read": a["read"], "location": a["location"],
        "value_relationship": a["value_relationship"], "bias": a["bias"],
        "regime": "balance" if a["state"] == "balance" else "trend",
        "bar_direction": "up" if close > o else "down" if close < o else "flat",
        "gamma_regime": gamma.get("regime") if gamma else None,
    }
    if gamma:
        context["gamma"] = {k: gamma.get(k) for k in ("proxy", "zero_gamma", "call_wall", "put_wall",
                                                      "calculated_at", "source")}
    dq = check_quality({
        "price": "degraded" if price_bad[i] else "clean",
        "volume": "degraded" if vol_bad[i] else "clean",
        "delta": "estimated",          # close-location estimate from OHLCV, not bid/ask
        "footprint": "unavailable",
        "gamma": "estimated" if gamma else "unavailable",   # ETF-proxy estimate live; none historically
    })
    return EventRecord(
        event_id=make_id(source, sym, tf, s.code, bar_open), timestamp=signal_time(bar_open, bar_s),
        bar_open=bar_open, symbol=sym, timeframe=tf, session=str(c["session"]), event=s.code,
        direction=s.direction, hypothesis=hypothesis, price=close, level=_r(s.level),
        context=context, data_quality=dq, source=source, detector=det)
