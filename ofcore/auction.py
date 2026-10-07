"""Auction market read: where's value, is it moving, is price accepted or rejected outside it."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import anchored_vwap, atr, cvd, ema, rvol, trading_day
from .profile import Profile, auto_bin_size, build_profile, naked_pocs, session_profiles


def value_relationship(cur: Profile, prev: Profile) -> str:
    """Classic two-day value area relationship."""
    if cur.val > prev.vah:
        return "higher"
    if cur.vah < prev.val:
        return "lower"
    if cur.vah >= prev.vah and cur.val <= prev.val:
        return "outside"
    if cur.vah <= prev.vah and cur.val >= prev.val:
        return "inside"
    return "overlapping-higher" if cur.poc > prev.poc else "overlapping-lower"


def _overlap(a: Profile, b: Profile) -> float:
    inter = max(0.0, min(a.vah, b.vah) - max(a.val, b.val))
    return inter / max(min(a.vah - a.val, b.vah - b.val), 1e-12)


def auction_read(df: pd.DataFrame, tick: float, balance_days: int = 5, accept_bars: int = 3,
                 va_pct: float = 0.70) -> dict:
    """Everything the dashboard/scanner needs about the current auction, in one dict."""
    bs = auto_bin_size(df, tick)
    comp = build_profile(df, bs, va_pct)
    sessions = session_profiles(df, auto_bin_size(df.tail(200), tick, rows=60), va_pct)
    last_close = float(df["close"].iloc[-1])
    a = float(atr(df).iloc[-1])
    notes: list[str] = []

    # --- balance vs imbalance over the last N sessions (or the bars themselves on daily) ---
    recent = sessions[-balance_days:] if len(sessions) >= balance_days else sessions
    bal_profile = build_profile(df[df.index >= recent[0].start], bs, va_pct) if recent else comp
    overlaps = [_overlap(x, y) for x, y in zip(recent, recent[1:])]
    pocs = np.array([s.poc for s in recent])
    slope = float(np.polyfit(np.arange(len(pocs)), pocs, 1)[0]) if len(pocs) >= 3 else 0.0
    migrating = abs(slope) * len(pocs) > 1.0 * a
    if overlaps and np.mean(overlaps) > 0.5 and not migrating:
        state = "balance"
        notes.append(f"{len(recent)}-session balance {bal_profile.val:g}–{bal_profile.vah:g}. "
                     "Fade the edges until one side gets accepted.")
    else:
        state = "imbalance-up" if slope > 0 else "imbalance-down"
        notes.append(f"Value migrating {'higher' if slope > 0 else 'lower'} "
                     f"({len(recent)} sessions, POC drift {slope * len(pocs):+.4g}). Trade with the drift, buy/sell value.")

    # --- value area relationship today vs prior ---
    rel = value_relationship(sessions[-1], sessions[-2]) if len(sessions) >= 2 else "n/a"

    # --- acceptance / rejection vs the balance value area ---
    ref = bal_profile
    tail = df.tail(accept_bars)
    above, below = (tail["close"] > ref.vah).all(), (tail["close"] < ref.val).all()
    window = df.tail(accept_bars * 4)
    poked_up = (window["high"] > ref.vah).any() and last_close < ref.vah
    poked_dn = (window["low"] < ref.val).any() and last_close > ref.val
    if above:
        location, read = "above value", "accepted above value"
        notes.append(f"{accept_bars} closes above VAH {ref.vah:g}. Acceptance, so look for continuation. "
                     f"VAH becomes support.")
    elif below:
        location, read = "below value", "accepted below value"
        notes.append(f"{accept_bars} closes below VAL {ref.val:g}. Acceptance, so look for continuation. "
                     f"VAL becomes resistance.")
    elif poked_up:
        location, read = "inside value", "look above and fail"
        notes.append(f"Probed above VAH {ref.vah:g} and got rejected back inside. 80% rule in play, "
                     f"so target POC {ref.poc:g} then VAL {ref.val:g}.")
    elif poked_dn:
        location, read = "inside value", "look below and fail"
        notes.append(f"Probed below VAL {ref.val:g} and got rejected back inside. 80% rule in play, "
                     f"so target POC {ref.poc:g} then VAH {ref.vah:g}.")
    else:
        location = "above value" if last_close > ref.vah else "below value" if last_close < ref.val else "inside value"
        read = "rotating"

    # --- orderflow-ish context: CVD vs price, RVOL, VWAPs, EMAs ---
    c = cvd(df, reset=None)
    n = min(len(df), 40)
    p_hi, p_lo = df["high"].tail(n), df["low"].tail(n)
    c_t = c.tail(n)
    divergence = None
    if p_hi.iloc[-5:].max() >= p_hi.max() and c_t.iloc[-5:].max() < c_t.max():
        divergence = "bearish"
        notes.append("Price at new highs but est. CVD isn't. Buyers are tiring and passive sellers may be absorbing.")
    elif p_lo.iloc[-5:].min() <= p_lo.min() and c_t.iloc[-5:].min() > c_t.min():
        divergence = "bullish"
        notes.append("Price at new lows but est. CVD isn't. Sellers are tiring and passive buyers may be absorbing.")

    rv = rvol(df)
    rv_last = float(rv.iloc[-1]) if pd.notna(rv.iloc[-1]) else None
    if rv_last and rv_last >= 2:
        notes.append(f"RVOL {rv_last:.1f}x. Initiative activity, so respect the move.")

    wv = anchored_vwap(df, "W")["vwap"].iloc[-1]
    mv = anchored_vwap(df, "M")["vwap"].iloc[-1]
    e21, e50 = ema(df["close"], 21).iloc[-1], ema(df["close"], 50).iloc[-1]
    trend = "up" if last_close > e21 > e50 else "down" if last_close < e21 < e50 else "mixed"

    score = {"balance": 0, "imbalance-up": 1, "imbalance-down": -1}[state]
    score += {"accepted above value": 1, "accepted below value": -1, "look above and fail": -1,
              "look below and fail": 1}.get(read, 0)
    score += {"up": 1, "down": -1}.get(trend, 0)
    score += {"bullish": 1, "bearish": -1}.get(divergence or "", 0)
    score += 0.5 if last_close > wv else -0.5
    bias = "long" if score >= 2 else "short" if score <= -2 else "neutral"

    npocs = naked_pocs(df, sessions)
    sess_last = sessions[-1] if sessions else comp
    levels = [
        ("Composite POC", comp.poc), ("Composite VAH", comp.vah), ("Composite VAL", comp.val),
        ("Balance VAH", ref.vah), ("Balance VAL", ref.val), ("Balance POC", ref.poc),
        ("Session POC", sess_last.poc), ("Session VAH", sess_last.vah), ("Session VAL", sess_last.val),
        ("Weekly VWAP", wv), ("Monthly VWAP", mv), ("EMA 21", e21), ("EMA 50", e50),
    ]
    levels += [("Naked POC", p["price"]) for p in npocs[-6:]]
    levels += [("LVN", x) for x in comp.lvns]
    lv = [{"name": k, "price": float(round(v, 8)), "dist": float(round(v - last_close, 8)),
           "dist_atr": float(round((v - last_close) / a, 2)) if a else None} for k, v in levels]
    lv.sort(key=lambda x: -x["price"])

    above_lv = [x for x in lv if x["price"] > last_close]
    below_lv = [x for x in lv if x["price"] < last_close]
    return {
        "last": last_close, "atr": a, "state": state, "value_relationship": rel, "location": location,
        "read": read, "divergence": divergence, "rvol": rv_last, "trend": trend, "bias": bias, "score": score,
        "composite": comp.to_dict(), "balance": ref.to_dict(with_bins=False),
        "sessions": [s.to_dict(with_bins=False) for s in sessions[-20:]],
        "naked_pocs": npocs, "levels": lv,
        "next_up": above_lv[-1] if above_lv else None, "next_down": below_lv[0] if below_lv else None,
        "notes": notes,
        "days": int(trading_day(df).nunique()),
    }
