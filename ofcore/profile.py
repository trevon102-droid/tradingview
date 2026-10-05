"""Volume profile: POC, value area, HVN/LVN, per-session profiles, naked POCs, poor highs/lows."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .indicators import is_daily, trading_day


@dataclass
class Profile:
    bin_size: float
    prices: np.ndarray  # bin floor prices
    volume: np.ndarray
    poc: float
    vah: float
    val: float
    high: float
    low: float
    hvns: list[float] = field(default_factory=list)
    lvns: list[float] = field(default_factory=list)
    poor_high: bool = False
    poor_low: bool = False
    start: pd.Timestamp | None = None
    end: pd.Timestamp | None = None

    def to_dict(self, with_bins: bool = True) -> dict:
        d = {k: _num(getattr(self, k)) for k in ["bin_size", "poc", "vah", "val", "high", "low"]}
        d.update(hvns=[_num(x) for x in self.hvns], lvns=[_num(x) for x in self.lvns],
                 poor_high=self.poor_high, poor_low=self.poor_low,
                 start=int(self.start.timestamp()) if self.start is not None else None,
                 end=int(self.end.timestamp()) if self.end is not None else None)
        if with_bins:
            d["bins"] = [[_num(p), float(v)] for p, v in zip(self.prices, self.volume) if v > 0]
        return d


def _num(x: float) -> float:
    return float(round(x, 8))


def auto_bin_size(df: pd.DataFrame, tick: float, rows: int = 120) -> float:
    """Bin = tick × a 'nice' multiplier (1, 2, 2.5, 5 × 10^k) giving roughly `rows` bins."""
    span = float(df["high"].max() - df["low"].min())
    raw = max(span / rows / tick, 1.0)  # ticks per bin
    mag = 10 ** math.floor(math.log10(raw))
    mult = next(m * mag for m in (1, 2, 2.5, 5, 10) if raw <= m * mag)
    return round(tick * max(1, math.ceil(mult)), 10)


def build_profile(df: pd.DataFrame, bin_size: float, va_pct: float = 0.70) -> Profile:
    lo_all = math.floor(df["low"].min() / bin_size)
    hi_all = math.floor(df["high"].max() / bin_size)
    nb = hi_all - lo_all + 1
    vol = np.zeros(nb)
    vols = df["volume"].to_numpy(float)
    if vols.sum() == 0:  # spot FX: no volume, profile by time (TPO-ish)
        vols = np.ones(len(df))
    for l, h, v in zip(df["low"].to_numpy(), df["high"].to_numpy(), vols):
        a, b = math.floor(l / bin_size) - lo_all, math.floor(h / bin_size) - lo_all
        vol[a:b + 1] += v / (b - a + 1)
    prices = (np.arange(nb) + lo_all) * bin_size

    poc_i = int(np.argmax(vol))
    lo_i = hi_i = poc_i
    target, acc = vol.sum() * va_pct, vol[poc_i]
    while acc < target and (lo_i > 0 or hi_i < nb - 1):
        up = vol[hi_i + 1] if hi_i < nb - 1 else -1
        dn = vol[lo_i - 1] if lo_i > 0 else -1
        if up >= dn:
            hi_i += 1
            acc += up
        else:
            lo_i -= 1
            acc += dn

    half = bin_size / 2
    hvns, lvns = _nodes(vol, prices + half)
    # Poor extreme = no excess: the edge bins still carry real volume relative to the POC.
    edge = max(1, nb // 25)
    return Profile(
        bin_size=bin_size, prices=prices, volume=vol,
        poc=prices[poc_i] + half, vah=prices[hi_i] + bin_size, val=prices[lo_i],
        high=float(df["high"].max()), low=float(df["low"].min()), hvns=hvns, lvns=lvns,
        poor_high=bool(nb > 5 and vol[-edge:].mean() > 0.35 * vol[poc_i]),
        poor_low=bool(nb > 5 and vol[:edge].mean() > 0.35 * vol[poc_i]),
        start=df.index[0], end=df.index[-1],
    )


def _nodes(vol: np.ndarray, centers: np.ndarray, k: int = 5) -> tuple[list[float], list[float]]:
    if len(vol) < 7:
        return [], []
    w = max(3, len(vol) // 30) | 1
    sm = np.convolve(vol, np.ones(w) / w, mode="same")
    peak, mean = sm.max(), sm.mean()
    hv, lv = [], []
    for i in range(1, len(sm) - 1):
        if sm[i] >= sm[i - 1] and sm[i] > sm[i + 1] and sm[i] > mean:
            hv.append((sm[i], centers[i]))
        elif sm[i] <= sm[i - 1] and sm[i] < sm[i + 1] and sm[i] < 0.6 * mean and sm[i] < 0.35 * peak:
            lv.append((sm[i], centers[i]))
    hv = [p for _, p in sorted(hv, reverse=True)[:k]]
    lv = [p for _, p in sorted(lv)[:k]]
    return sorted(hv), sorted(lv)


def session_profiles(df: pd.DataFrame, bin_size: float, va_pct: float = 0.70) -> list[Profile]:
    """One profile per trading day — or per week when you feed it daily bars."""
    td = trading_day(df)
    key = td.dt.to_period("W-SUN").astype(str) if is_daily(df) else td
    return [build_profile(g, bin_size, va_pct) for _, g in df.groupby(key.values) if len(g) >= 3]


def naked_pocs(df: pd.DataFrame, sessions: list[Profile]) -> list[dict]:
    """Prior-session POCs price hasn't traded back through yet — the classic swing magnets."""
    out = []
    for s in sessions[:-1]:
        later = df[df.index > s.end]
        if later.empty:
            continue
        touched = ((later["low"] <= s.poc) & (later["high"] >= s.poc)).any()
        if not touched:
            out.append({"price": _num(s.poc), "session": int(s.start.timestamp())})
    return out
