"""Aggressor-tagged trade + order book feeds for the footprint / DOM.

    sim        synthetic tape (offline, for testing). Always badged SIM in the UI.
    kraken     BTC / ETH. Free public websocket: every trade has its taker side + L2 book.
    databento  CME futures (ES, NQ, MES, MNQ, YM, CL, GC). Needs DATABENTO_API_KEY (paid, usage-based).

A feed calls on_trade(ts, price, size, is_buy) and on_book(bids, asks, snapshot) where bids/asks are
[(price, size), ...] and size 0 removes a level.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from dataclasses import dataclass
from typing import Callable

OnTrade = Callable[[float, float, float, bool], None]
OnBook = Callable[[list, list, bool], None]


@dataclass(frozen=True)
class FPSym:
    key: str
    name: str
    tick: float
    row_ticks: int       # default footprint row size
    feed: str            # live feed for this market
    feed_symbol: str
    sim_price: float
    lot: float           # size granularity: 1 contract, or fractional coins


FP_SYMBOLS: dict[str, FPSym] = {s.key: s for s in [
    FPSym("ES", "E-mini S&P 500", 0.25, 1, "databento", "ES.c.0", 5800, 1),
    FPSym("NQ", "E-mini Nasdaq 100", 0.25, 4, "databento", "NQ.c.0", 20500, 1),
    FPSym("MES", "Micro S&P 500", 0.25, 1, "databento", "MES.c.0", 5800, 1),
    FPSym("MNQ", "Micro Nasdaq 100", 0.25, 4, "databento", "MNQ.c.0", 20500, 1),
    FPSym("YM", "E-mini Dow", 1.0, 2, "databento", "YM.c.0", 42500, 1),
    FPSym("CL", "Crude Oil", 0.01, 2, "databento", "CL.c.0", 72, 1),
    FPSym("GC", "Gold", 0.1, 2, "databento", "GC.c.0", 2650, 1),
    FPSym("BTC", "Bitcoin (Kraken)", 0.1, 50, "kraken", "BTC/USD", 98000, 0.0001),
    FPSym("ETH", "Ethereum (Kraken)", 0.01, 50, "kraken", "ETH/USD", 3400, 0.001),
]}


def make_feed(sym: FPSym, mode: str = "live"):
    if mode == "sim" or os.environ.get("OF_DATA") == "demo":
        return SimFeed(sym)
    if sym.feed == "kraken":
        return KrakenFeed(sym)
    if sym.feed == "databento":
        return DatabentoFeed(sym)
    raise ValueError(sym.feed)


class Feed:
    name = "base"
    live = True

    def __init__(self, sym: FPSym):
        self.sym = sym
        self.status = "connecting"
        self.error: str | None = None

    async def run(self, on_trade: OnTrade, on_book: OnBook) -> None:  # pragma: no cover
        raise NotImplementedError


# ───────────────────────── SIM ─────────────────────────

class SimFeed(Feed):
    """Random-walk tape with order-flow structure: drifts, absorption at levels, size clusters."""
    name = "sim"
    live = False

    def __init__(self, sym: FPSym, seed: int | None = None, rate: float = 12.0, backfill_min: int = 180):
        super().__init__(sym)
        self.rng = random.Random(seed if seed is not None else sum(map(ord, sym.key)))
        self.rate, self.backfill_min = rate, backfill_min
        # crypto tick is tiny relative to price: walk in bigger steps so the tape looks like the real thing
        self.step = sym.tick * (max(1, sym.row_ticks // 2) if sym.lot < 1 else 1)
        self.mid = round(sym.sim_price / self.step) * self.step
        self.drift = 0.0
        self.absorb_px: float | None = None
        self.book_bid: dict[int, float] = {}
        self.book_ask: dict[int, float] = {}

    def _size(self) -> float:
        r = self.rng
        x = r.lognormvariate(0.3, 1.0) * (8 if r.random() < 0.03 else 1)  # occasional block print
        if self.sym.lot < 1:
            x *= 0.05
        return max(self.sym.lot, round(x / self.sym.lot) * self.sym.lot) if self.sym.lot < 1 else max(1, int(x))

    def _step(self) -> tuple[float, float, bool]:
        r, t = self.rng, self.step
        if r.random() < 0.002:
            self.drift = r.choice([-1, 0, 0, 1]) * r.uniform(0.15, 0.35)
        if self.absorb_px is None and r.random() < 0.0015:
            self.absorb_px = self.mid + r.choice([-1, 1]) * t * r.randint(2, 6)
        elif self.absorb_px is not None and r.random() < 0.01:
            self.absorb_px = None
        p_buy = min(0.85, max(0.15, 0.5 + self.drift))
        is_buy = r.random() < p_buy
        # a passive wall soaks up aggression: price can't get through it
        if self.absorb_px is not None and ((is_buy and self.mid + t >= self.absorb_px) or
                                           (not is_buy and self.mid - t <= self.absorb_px)):
            return self.absorb_px, self._size() * 2, is_buy
        if r.random() < 0.05:
            self.mid += t if is_buy else -t
        price = self.mid + (t if is_buy else 0)  # buyers lift the offer, sellers hit the bid
        return round(round(price / t) * t, 10), self._size(), is_buy

    def _book(self) -> tuple[list, list]:
        t, r = self.sym.tick * max(1, self.sym.row_ticks // 5), self.rng  # same grouping the DOM uses
        bid0 = round(self.mid / t)
        base = 20 if self.sym.lot >= 1 else 2.0

        def level(row: int, depth: int) -> tuple[float, float]:
            px = round(row * t, 10)
            wall = 6 if self.absorb_px is not None and abs(px - self.absorb_px) < t / 2 else 1
            return px, round(base * r.uniform(0.4, 1.6) * (1 + depth / 15) * wall, 4)

        return [level(bid0 - i, i) for i in range(60)], [level(bid0 + 1 + i, i) for i in range(60)]

    def backfill(self, on_trade: OnTrade, now: float | None = None) -> None:
        now = now or time.time()
        ts = now - self.backfill_min * 60
        while ts < now:
            px, sz, b = self._step()
            on_trade(ts, px, sz, b)
            ts += self.rng.expovariate(self.rate)

    async def run(self, on_trade: OnTrade, on_book: OnBook) -> None:
        self.backfill(on_trade)
        on_book(*self._book(), True)
        self.status = "sim"
        last_book = 0.0
        while True:
            await asyncio.sleep(self.rng.expovariate(self.rate))
            px, sz, b = self._step()
            on_trade(time.time(), px, sz, b)
            if time.time() - last_book > 0.25:
                bids, asks = self._book()
                on_book(bids, asks, True)
                last_book = time.time()


# ───────────────────────── KRAKEN (crypto) ─────────────────────────

class KrakenFeed(Feed):
    name = "kraken"
    WS = "wss://ws.kraken.com/v2"
    REST = "https://api.kraken.com/0/public/Trades"
    REST_PAIR = {"BTC/USD": "XBTUSD", "ETH/USD": "ETHUSD"}

    def __init__(self, sym: FPSym, backfill_min: int = 120):
        super().__init__(sym)
        self.backfill_min = backfill_min

    def _backfill(self) -> list[tuple[float, float, float, bool]]:
        import requests

        since = int((time.time() - self.backfill_min * 60) * 1e9)
        out: list[tuple[float, float, float, bool]] = []
        for _ in range(30):  # ~1000 trades per page; Kraken rate-limits public REST at ~1 req/s
            r = requests.get(self.REST, params={"pair": self.REST_PAIR[self.sym.feed_symbol], "since": since}, timeout=10)
            js = r.json()
            if js.get("error"):
                raise RuntimeError(js["error"])
            res = js["result"]
            rows = next(v for k, v in res.items() if k != "last")
            out += [(float(t[2]), float(t[0]), float(t[1]), t[3] == "b") for t in rows]
            since = int(res["last"])
            if len(rows) < 1000:
                break
            time.sleep(1.1)
        return out

    async def run(self, on_trade: OnTrade, on_book: OnBook) -> None:
        import websockets

        try:
            for tr in await asyncio.to_thread(self._backfill):
                on_trade(*tr)
        except Exception as e:  # backfill is a nice-to-have; live stream still works without it
            self.error = f"backfill failed: {e}"
        backoff = 1
        while True:
            try:
                async with websockets.connect(self.WS, ping_interval=20, max_size=2**22) as ws:
                    for ch in ({"channel": "trade", "snapshot": False},
                               {"channel": "book", "depth": 100}):
                        await ws.send(json.dumps({"method": "subscribe",
                                                  "params": {**ch, "symbol": [self.sym.feed_symbol]}}))
                    self.status, self.error, backoff = "live", None, 1
                    async for raw in ws:
                        self.handle(json.loads(raw), on_trade, on_book)
            except Exception as e:
                self.status, self.error = "reconnecting", str(e)[:200]
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)


    @staticmethod
    def handle(msg: dict, on_trade: OnTrade, on_book: OnBook) -> None:
        """Kraken v2: trade side is the taker (aggressor) side; book qty 0 deletes a level."""
        ch = msg.get("channel")
        if ch == "trade":
            for t in msg.get("data", []):
                on_trade(_iso_ts(t["timestamp"]), float(t["price"]), float(t["qty"]), t["side"] == "buy")
        elif ch == "book":
            for d in msg.get("data", []):
                on_book([(float(x["price"]), float(x["qty"])) for x in d.get("bids", [])],
                        [(float(x["price"]), float(x["qty"])) for x in d.get("asks", [])],
                        msg.get("type") == "snapshot")


def _iso_ts(s: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


# ───────────────────────── DATABENTO (CME futures) ─────────────────────────

class DatabentoFeed(Feed):
    """CME Globex via Databento live: `trades` (aggressor side on every print) + `mbp-10` (top-10 book).
    Replays the last `backfill_min` minutes on connect so the footprint isn't empty."""
    name = "databento"
    DATASET = "GLBX.MDP3"

    def __init__(self, sym: FPSym, backfill_min: int = 120):
        super().__init__(sym)
        self.backfill_min = backfill_min

    async def run(self, on_trade: OnTrade, on_book: OnBook) -> None:
        key = os.environ.get("DATABENTO_API_KEY")
        if not key:
            self.status, self.error = "no key", "Set DATABENTO_API_KEY for live CME data (or switch the feed to SIM)."
            return
        loop = asyncio.get_running_loop()
        backoff = 1
        while True:
            try:
                await asyncio.to_thread(self._stream, key, loop, on_trade, on_book)
            except Exception as e:
                self.status, self.error = "reconnecting", str(e)[:200]
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    def _stream(self, key: str, loop: asyncio.AbstractEventLoop, on_trade: OnTrade, on_book: OnBook) -> None:
        import databento as db

        scale = 1e9  # Databento fixed-point prices
        client = db.Live(key=key)
        start = int((time.time() - self.backfill_min * 60) * 1e9)
        client.subscribe(dataset=self.DATASET, schema="trades", stype_in="continuous",
                         symbols=[self.sym.feed_symbol], start=start)
        client.subscribe(dataset=self.DATASET, schema="mbp-10", stype_in="continuous",
                         symbols=[self.sym.feed_symbol])
        self.status, self.error = "live", None
        for rec in client:
            if isinstance(rec, db.TradeMsg):
                side = _side(rec.side)
                if side in ("A", "B"):  # B = buy aggressor, A = sell aggressor, N = unknown
                    loop.call_soon_threadsafe(on_trade, rec.ts_event / 1e9, rec.price / scale, float(rec.size), side == "B")
            elif isinstance(rec, db.MBP10Msg):
                bids = [(lv.bid_px / scale, float(lv.bid_sz)) for lv in rec.levels if lv.bid_sz > 0]
                asks = [(lv.ask_px / scale, float(lv.ask_sz)) for lv in rec.levels if lv.ask_sz > 0]
                loop.call_soon_threadsafe(on_book, bids, asks, True)
            elif isinstance(rec, db.ErrorMsg):
                raise RuntimeError(rec.err)


def _side(s) -> str:
    s = getattr(s, "value", s)
    return chr(s) if isinstance(s, int) else str(s)
