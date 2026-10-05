"""Personal orderflow dashboard. Run from repo root:  uvicorn dashboard.app:app --reload"""

from __future__ import annotations

import math
import time
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ofcore import (SYMBOLS, anchor_key, anchored_vwap, auction_read, cvd, ema, est_delta, gamma_levels, get_bars,
                    rvol, trading_day)

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Orderflow Desk")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_cache: dict[tuple, tuple[float, object]] = {}


def cached(key: tuple, ttl: float, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


def _series(idx: pd.DatetimeIndex, s: pd.Series, breaks: pd.Series | None = None) -> list[dict]:
    """Line points. Bars flagged in `breaks` get a transparent segment so anchored lines don't join across resets."""
    brk = breaks.to_numpy() if breaks is not None else [False] * len(idx)
    out = []
    for t, v, b in zip(idx, s, brk):
        if math.isnan(v):
            continue
        p = {"time": int(t.timestamp()), "value": float(v)}
        if b:
            p["color"] = "rgba(0,0,0,0)"
        out.append(p)
    return out


def _resets(df: pd.DataFrame, anchor: str) -> pd.Series:
    """True on the last bar of each anchor period (lightweight-charts colors a segment by its start point)."""
    key = anchor_key(df, anchor)
    return key.ne(key.shift(-1)) & key.shift(-1).notna()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/symbols")
def symbols():
    return [{"key": s.key, "name": s.name, "kind": s.kind, "gamma": bool(s.gamma_proxy)} for s in SYMBOLS.values()]


def _bars(sym: str, tf: str, days: int) -> pd.DataFrame:
    if sym not in SYMBOLS:
        raise HTTPException(404, f"unknown symbol {sym}")
    try:
        return cached(("bars", sym, tf, days), 120, lambda: get_bars(sym, tf, days))
    except Exception as e:  # network / provider errors -> readable message in the UI
        raise HTTPException(502, f"data error for {sym}: {e}") from e


@app.get("/api/chart")
def chart(sym: str = "ES", tf: str = "1h", days: int = 60):
    df = _bars(sym, tf, days)
    idx = df.index
    w, m = anchored_vwap(df, "W"), anchored_vwap(df, "M")
    d = est_delta(df)
    return {
        "symbol": sym, "tf": tf, "tick": SYMBOLS[sym].tick,
        "bars": [{"time": int(t.timestamp()), "open": o, "high": h, "low": l, "close": c, "volume": v}
                 for t, o, h, l, c, v in zip(idx, *(df[k].astype(float) for k in ["open", "high", "low", "close", "volume"]))],
        "ema": {str(n): _series(idx, ema(df["close"], n)) for n in (9, 21, 50, 200)},
        "vwap_w": {k: _series(idx, w[k], _resets(df, "W")) for k in w},
        "vwap_m": {k: _series(idx, m[k], _resets(df, "M")) for k in ("vwap",)},
        "delta": _series(idx, d),
        "cvd": _series(idx, cvd(df, reset=None)),
        "rvol": _series(idx, rvol(df).fillna(0)),
        "auction": auction_read(df, SYMBOLS[sym].tick),
    }


@app.get("/api/gamma")
def gamma(sym: str = "ES"):
    if sym not in SYMBOLS:
        raise HTTPException(404, f"unknown symbol {sym}")
    df = _bars(sym, "1h", 10)
    try:
        g = cached(("gamma", sym), 900, lambda: gamma_levels(sym, float(df["close"].iloc[-1])))
    except Exception as e:
        raise HTTPException(502, f"options data error: {e}") from e
    return g or {"unavailable": True}


@app.get("/api/watchlist")
def watchlist(tf: str = "1h", days: int = 30):
    out = []
    for key in SYMBOLS:
        try:
            df = _bars(key, tf, days)
            a = cached(("read", key, tf, days), 120, lambda: auction_read(df, SYMBOLS[key].tick))
            td = trading_day(df)
            prior = df["close"][td < td.iloc[-1]]
            last = float(df["close"].iloc[-1])
            prev = float(prior.iloc[-1]) if len(prior) else float(df["open"].iloc[0])
            out.append({"key": key, "last": last, "chg": (last / prev - 1) * 100, "state": a["state"],
                        "read": a["read"], "bias": a["bias"]})
        except Exception as e:
            out.append({"key": key, "error": str(e)[:120]})
    return out
