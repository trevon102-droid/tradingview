"""Setup detection on top of the auction read — what the scanner alerts on."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from .auction import auction_read
from .indicators import anchored_vwap, ema


@dataclass
class Signal:
    symbol: str
    code: str
    direction: str  # long | short | info
    text: str
    price: float

    def key(self, bar_time: int) -> str:
        """One alert per setup *event*: the bar (unix sec) where it switched on."""
        return f"{self.symbol}:{self.code}:{bar_time}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Thresholds:
    edge_atr: float = 0.3   # "at the edge" of balance
    npoc_atr: float = 0.5   # near a naked POC
    gamma_atr: float = 0.3  # near zero gamma
    rvol: float = 2.0


def detect(sym: str, df: pd.DataFrame, a: dict, gamma: dict | None = None, th: Thresholds = Thresholds()) -> list[Signal]:
    out: list[Signal] = []
    px, atr = a["last"], a["atr"] or 1e-9
    add = lambda code, d, t: out.append(Signal(sym, code, d, t, px))  # noqa: E731
    bal = a["balance"]

    read = a["read"]
    if read == "accepted above value":
        add("accept_above", "long", f"Accepted above value (VAH {bal['vah']:g}). Buy pullbacks into VAH.")
    elif read == "accepted below value":
        add("accept_below", "short", f"Accepted below value (VAL {bal['val']:g}). Sell rallies into VAL.")
    elif read == "look above and fail":
        add("lookabove_fail", "short", f"Look above and fail at {bal['vah']:g}. Targets POC {bal['poc']:g}, then VAL {bal['val']:g}.")
    elif read == "look below and fail":
        add("lookbelow_fail", "long", f"Look below and fail at {bal['val']:g}. Targets POC {bal['poc']:g}, then VAH {bal['vah']:g}.")

    if a["state"] == "balance":
        if abs(px - bal["vah"]) <= th.edge_atr * atr:
            add("balance_edge_high", "short", f"At balance high {bal['vah']:g}. Fade unless it gets accepted.")
        elif abs(px - bal["val"]) <= th.edge_atr * atr:
            add("balance_edge_low", "long", f"At balance low {bal['val']:g}. Fade unless it gets accepted.")

    for n in a["naked_pocs"]:
        if abs(px - n["price"]) <= th.npoc_atr * atr:
            d = "short" if n["price"] > px else "long"
            add("naked_poc", "info", f"Within {th.npoc_atr} ATR of naked POC {n['price']:g} (magnet / reaction zone, {d} side).")
            break

    if a["divergence"]:
        d = "long" if a["divergence"] == "bullish" else "short"
        add(f"cvd_div_{a['divergence']}", d, f"{a['divergence'].title()} CVD divergence. Aggression is fading at the extreme.")

    if a["rvol"] and a["rvol"] >= th.rvol:
        add("rvol", "info", f"RVOL {a['rvol']:.1f}x. Initiative participation.")

    # trend pullback to weekly VWAP with the EMA stack behind it
    wv = anchored_vwap(df, "W")["vwap"]
    e21, e50 = ema(df["close"], 21), ema(df["close"], 50)
    last = df.iloc[-1]
    if e21.iloc[-1] > e50.iloc[-1] and last["low"] <= wv.iloc[-1] < last["close"]:
        add("vwap_pullback_long", "long", f"Uptrend pullback held weekly VWAP {wv.iloc[-1]:.6g}.")
    elif e21.iloc[-1] < e50.iloc[-1] and last["high"] >= wv.iloc[-1] > last["close"]:
        add("vwap_pullback_short", "short", f"Downtrend rally rejected weekly VWAP {wv.iloc[-1]:.6g}.")

    if gamma and gamma.get("zero_gamma"):
        zg = gamma["zero_gamma"]
        prev = float(df["close"].iloc[-2])
        if (prev - zg) * (px - zg) < 0:
            regime = "negative γ, so expect expansion" if px < zg else "positive γ, so expect mean reversion"
            add("gamma_flip_cross", "info", f"Crossed est. zero gamma {zg:g} ({regime}).")
        elif abs(px - zg) <= th.gamma_atr * atr:
            add("gamma_flip_near", "info", f"Sitting on est. zero gamma {zg:g}. Vol regime can flip here.")
        for name in ("call_wall", "put_wall"):
            lvl = gamma.get(name)
            if lvl and abs(px - lvl) <= th.gamma_atr * atr:
                add(name, "info", f"At est. {name.replace('_', ' ')} {lvl:g}. Dealer hedging tends to pin/reject here.")
    return out


def closed_bars(df: pd.DataFrame, bar: pd.Timedelta, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Drop the still-forming last bar. Signals on an unfinished candle flicker on and off."""
    now = now or pd.Timestamp.now(tz="UTC")
    return df.iloc[:-1] if len(df) and df.index[-1] + bar > now else df


def events(sym: str, df: pd.DataFrame, tick: float, gamma: dict | None = None, th: Thresholds = Thresholds(),
           lookback: int = 3) -> tuple[list[tuple[str, Signal]], dict]:
    """Setups that switched ON within the last `lookback` closed bars, keyed by the bar they fired on.

    A setup that stays on doesn't re-alert. If it turns off and later on again (e.g. accepted above
    value, fell back in, accepted again), that's a new event with a new key. Uses only bars up to each
    evaluation point, so no look-ahead. Returns (events newest first, auction read of the latest bar)."""
    states, reads = [], []
    for k in range(lookback + 1):
        sub = df.iloc[: len(df) - k]
        a = auction_read(sub, tick)
        reads.append(a)
        states.append({s.code: s for s in detect(sym, sub, a, gamma, th)})
    out = []
    for k in range(lookback):
        bar_t = int(df.index[len(df) - 1 - k].timestamp())
        for code in states[k].keys() - states[k + 1].keys():
            out.append((states[k][code].key(bar_t), states[k][code]))
    return out, reads[0]
