"""Dealer gamma exposure (GEX) from an options chain, mapped onto the futures price.

Convention (SpotGamma-style): dealers are assumed long calls / short puts from customer flow, so
call gamma counts +, put gamma counts −. GEX per strike is dollar gamma per 1% move:
    gamma × OI × 100 × S² × 0.01
Above the zero-gamma flip dealers hedge against the move (mean reversion, vol compression).
Below it they hedge with the move (trend, vol expansion). Treat it as context, not a signal.

Futures don't have a free options chain, so we use the matching ETF (SPY for ES, QQQ for NQ, GLD
for GC, ...) and scale strikes by the futures/ETF price ratio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import SYMBOLS

RATE = 0.04


@dataclass
class OptRow:
    strike: float
    is_call: bool
    oi: float
    iv: float
    t: float  # years to expiry


def bs_gamma(s: np.ndarray | float, k: float, t: float, iv: float, r: float = RATE) -> np.ndarray:
    s = np.asarray(s, float)
    if t <= 0 or iv <= 0:
        return np.zeros_like(s)
    d1 = (np.log(s / k) + (r + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
    return np.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi) / (s * iv * math.sqrt(t))


def gex_by_strike(rows: list[OptRow], spot: float) -> pd.DataFrame:
    recs = []
    for o in rows:
        g = float(bs_gamma(spot, o.strike, o.t, o.iv)) * o.oi * 100 * spot * spot * 0.01
        recs.append((o.strike, g if o.is_call else 0.0, -g if not o.is_call else 0.0))
    df = pd.DataFrame(recs, columns=["strike", "call_gex", "put_gex"]).groupby("strike").sum()
    df["net_gex"] = df["call_gex"] + df["put_gex"]
    return df


def total_gex_curve(rows: list[OptRow], spots: np.ndarray) -> np.ndarray:
    tot = np.zeros_like(spots, dtype=float)
    for o in rows:
        g = bs_gamma(spots, o.strike, o.t, o.iv) * o.oi * 100 * spots * spots * 0.01
        tot += g if o.is_call else -g
    return tot


def zero_gamma(rows: list[OptRow], spot: float, width: float = 0.12) -> float | None:
    """Price where net dealer gamma flips sign, closest to spot."""
    spots = np.linspace(spot * (1 - width), spot * (1 + width), 241)
    curve = total_gex_curve(rows, spots)
    flips = np.where(np.diff(np.sign(curve)) != 0)[0]
    if len(flips) == 0:
        return None
    pts = [spots[i] - curve[i] * (spots[i + 1] - spots[i]) / (curve[i + 1] - curve[i]) for i in flips]
    return float(min(pts, key=lambda p: abs(p - spot)))


def levels_from_chain(rows: list[OptRow], spot: float) -> dict:
    by = gex_by_strike(rows, spot)
    near = by[(by.index > spot * 0.85) & (by.index < spot * 1.15)]
    if near.empty:
        near = by
    flip = zero_gamma(rows, spot)
    total = float(by["net_gex"].sum())
    top = near["net_gex"].abs().sort_values(ascending=False).head(6).index
    return {
        "spot": spot,
        "total_gex": total,
        "regime": "positive" if total > 0 else "negative",
        "zero_gamma": flip,
        "call_wall": float(near["call_gex"].idxmax()),
        "put_wall": float(near["put_gex"].idxmin()),
        "major_strikes": sorted(float(k) for k in top),
        "profile": [[float(k), float(v)] for k, v in near["net_gex"].items()],
    }


def fetch_chain_yahoo(etf: str, max_expiries: int = 6, max_days: int = 45) -> tuple[list[OptRow], float]:
    import yfinance as yf

    tk = yf.Ticker(etf)
    spot = float(tk.history(period="5d")["Close"].iloc[-1])
    now = pd.Timestamp.now(tz="UTC")
    rows: list[OptRow] = []
    for exp in tk.options[:max_expiries]:
        t_exp = pd.Timestamp(exp, tz="America/New_York") + pd.Timedelta(hours=16)
        days = (t_exp - now).total_seconds() / 86400
        if days > max_days:
            break
        t = max(days, 0.25) / 365
        ch = tk.option_chain(exp)
        for frame, is_call in ((ch.calls, True), (ch.puts, False)):
            for k, oi, iv in frame[["strike", "openInterest", "impliedVolatility"]].fillna(0).itertuples(index=False):
                if oi > 0 and iv > 0.01:
                    rows.append(OptRow(float(k), is_call, float(oi), float(iv), t))
    return rows, spot


def demo_chain(spot: float) -> list[OptRow]:
    """Synthetic chain shaped like a typical index ETF (put-heavy below, call wall above)."""
    rng = np.random.default_rng(7)
    step = 10 ** math.floor(math.log10(spot / 100))
    rows = []
    for t in (2 / 365, 9 / 365, 30 / 365):
        for k in np.arange(round(spot * 0.85 / step) * step, spot * 1.15, step):
            m = (k - spot) / spot
            iv = 0.16 - 0.5 * m + 0.8 * m * m
            rows.append(OptRow(float(k), True, float(rng.gamma(2, 4000) * np.exp(-((m - 0.03) / 0.04) ** 2)), iv, t))
            rows.append(OptRow(float(k), False, float(rng.gamma(2, 5000) * np.exp(-((m + 0.04) / 0.05) ** 2)), iv, t))
    return rows


def gamma_levels(key: str, fut_price: float, provider: str | None = None) -> dict | None:
    """Gamma levels in *futures* price terms. None if the market has no options proxy."""
    import os

    sym = SYMBOLS[key]
    if not sym.gamma_proxy:
        return None
    provider = provider or os.environ.get("OF_DATA", "yahoo")
    if provider == "demo":
        etf_spot = fut_price / 10 if key == "ES" else fut_price / 40 if key == "NQ" else fut_price
        rows = demo_chain(etf_spot)
    else:
        rows, etf_spot = fetch_chain_yahoo(sym.gamma_proxy)
    if not rows:
        return None
    lv = levels_from_chain(rows, etf_spot)
    ratio = fut_price / etf_spot
    m = lambda x: None if x is None else round(x * ratio / sym.tick) * sym.tick  # noqa: E731
    out = {
        "proxy": sym.gamma_proxy, "ratio": ratio, "regime": lv["regime"], "total_gex": lv["total_gex"],
        "etf": {k: lv[k] for k in ("spot", "zero_gamma", "call_wall", "put_wall", "major_strikes")},
        "zero_gamma": m(lv["zero_gamma"]), "call_wall": m(lv["call_wall"]), "put_wall": m(lv["put_wall"]),
        "major_strikes": [m(x) for x in lv["major_strikes"]],
        "profile": [[m(k), v] for k, v in lv["profile"]],
    }
    if lv["zero_gamma"] is not None:
        out["regime"] = "positive" if etf_spot > lv["zero_gamma"] else "negative"
    out["pine"] = pine_string(out)
    return out


def pine_string(g: dict) -> str:
    """Paste-ready input for pine/gamma_levels.pine."""
    zg = g["zero_gamma"] if g["zero_gamma"] is not None else 0
    majors = ",".join(f"{x:g}" for x in g["major_strikes"])
    return f"{zg:g};{g['call_wall']:g};{g['put_wall']:g};{majors}"
