"""Personal orderflow dashboard. Run from repo root:  uvicorn dashboard.app:app --reload

Binds to localhost by default. If you ever expose it (--host 0.0.0.0, a VPS...), set OF_TOKEN and open
the page once with ?token=<OF_TOKEN>; it sets a cookie. Better still, keep it behind Tailscale/Cloudflare Access.
"""

from __future__ import annotations

import math
import os
import secrets
import time
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from ofcore import (SYMBOLS, anchor_key, anchored_vwap, auction_read, cvd, ema, est_delta, gamma_levels, get_bars,
                    rvol, trading_day)
from ofcore.feeds import FP_SYMBOLS

from . import footprint_hub

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Orderflow Desk")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_cache: dict[tuple, tuple[float, object]] = {}

TOKEN = os.environ.get("OF_TOKEN")
TF = Query("1h", pattern="^(1h|4h|1d)$")


def _authorized(token: str | None) -> bool:
    return not TOKEN or (token is not None and secrets.compare_digest(token, TOKEN))


@app.middleware("http")
async def auth(request: Request, call_next):
    q = request.query_params.get("token")
    bearer = request.headers.get("authorization", "").removeprefix("Bearer ").strip() or None
    if not any(_authorized(t) for t in (q, request.cookies.get("of_token"), bearer)):
        return PlainTextResponse("unauthorized: open with ?token=<OF_TOKEN>", status_code=401)
    resp = await call_next(request)
    if TOKEN and q and _authorized(q):
        resp.set_cookie("of_token", q, httponly=True, samesite="strict")
    return resp


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


@app.get("/footprint")
def footprint_page():
    return FileResponse(STATIC / "footprint.html")


@app.get("/api/fp/symbols")
def fp_symbols():
    return [{"key": s.key, "name": s.name, "tick": s.tick, "row_ticks": s.row_ticks, "feed": s.feed}
            for s in FP_SYMBOLS.values()]


@app.websocket("/ws/footprint")
async def ws_footprint(ws: WebSocket,
                       sym: str = Query("ES", max_length=12),
                       mode: str = Query("live", pattern="^(live|sim)$"),
                       bar: int = Query(300, ge=15, le=86_400),
                       row: int = Query(0, ge=0, le=10_000),
                       ratio: float = Query(3.0, ge=1.0, le=20.0, allow_inf_nan=False),
                       stack: int = Query(3, ge=2, le=20)):
    # websockets skip HTTP middleware, so check the token here (cookie is sent on same-origin upgrades)
    if not any(_authorized(t) for t in (ws.query_params.get("token"), ws.cookies.get("of_token"))):
        await ws.close(code=1008)
        return
    row = row or (FP_SYMBOLS[sym].row_ticks if sym in FP_SYMBOLS else 1)
    await footprint_hub.serve(ws, sym, mode, bar, row, ratio, stack)


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
def chart(sym: str = Query("ES", max_length=12), tf: str = TF, days: int = Query(60, ge=5, le=730)):
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
def gamma(sym: str = Query("ES", max_length=12)):
    if sym not in SYMBOLS:
        raise HTTPException(404, f"unknown symbol {sym}")
    df = _bars(sym, "1h", 10)
    try:
        g = cached(("gamma", sym), 900, lambda: gamma_levels(sym, float(df["close"].iloc[-1])))
    except Exception as e:
        raise HTTPException(502, f"options data error: {e}") from e
    if not g:
        return {"unavailable": True}
    from ofcore.gamma import freshness
    return {**g, **freshness(g)}


@app.get("/api/watchlist")
def watchlist(tf: str = TF, days: int = Query(30, ge=5, le=730)):
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
