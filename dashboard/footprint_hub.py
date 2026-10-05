"""One running feed per (market, mode), fanned out to every connected footprint/DOM client."""

from __future__ import annotations

import asyncio
from collections import deque

from fastapi import WebSocket, WebSocketDisconnect

from ofcore.feeds import FP_SYMBOLS, make_feed
from ofcore.footprint import Book, FootprintBuilder

RAW_KEEP = 400_000  # raw prints kept so a client can switch bar/row size without losing history


class Hub:
    def __init__(self, key: str, mode: str):
        self.sym = FP_SYMBOLS[key]
        self.feed = make_feed(self.sym, mode)
        self.book = Book()
        self.raw: deque[tuple[float, float, float, bool]] = deque(maxlen=RAW_KEEP)
        self.builders: dict[tuple[int, int], FootprintBuilder] = {}
        self.tape: deque[tuple[float, float, float, bool]] = deque(maxlen=200)
        self.seq = 0  # bumps on every print, so clients can tell what's new
        self.task = asyncio.create_task(self.feed.run(self.on_trade, self.on_book))

    def on_trade(self, ts: float, price: float, size: float, is_buy: bool) -> None:
        tr = (ts, price, size, is_buy)
        self.raw.append(tr)
        self.tape.append(tr)
        self.seq += 1
        for b in self.builders.values():
            b.on_trade(*tr)

    def on_book(self, bids: list, asks: list, snapshot: bool) -> None:
        if snapshot:
            self.book.reset()
        for p, s in bids:
            self.book.set("bid", p, s)
        for p, s in asks:
            self.book.set("ask", p, s)

    def builder(self, bar_seconds: int, row_ticks: int) -> FootprintBuilder:
        k = (bar_seconds, row_ticks)
        if k not in self.builders:
            b = FootprintBuilder(self.sym.tick, bar_seconds, row_ticks)
            for tr in self.raw:
                b.on_trade(*tr)
            self.builders[k] = b
        return self.builders[k]

    def meta(self) -> dict:
        f = self.feed
        return {"sym": self.sym.key, "name": self.sym.name, "tick": self.sym.tick, "feed": f.name,
                "live": f.live, "status": f.status, "error": f.error}


_hubs: dict[tuple[str, str], Hub] = {}


def get_hub(key: str, mode: str) -> Hub:
    k = (key, mode)
    hub = _hubs.get(k)
    if hub is None or (hub.task.done() and hub.feed.status != "no key"):
        hub = _hubs[k] = Hub(key, mode)
    return hub


async def serve(ws: WebSocket, key: str, mode: str, bar_seconds: int, row_ticks: int, ratio: float, stack: int) -> None:
    await ws.accept()
    if key not in FP_SYMBOLS:
        await ws.send_json({"type": "error", "error": f"unknown symbol {key}"})
        await ws.close()
        return
    hub = get_hub(key, mode)
    await asyncio.sleep(0.3)  # let a fresh sim/backfill seed a little first
    b = hub.builder(bar_seconds, row_ticks)
    seq = hub.seq
    await ws.send_json({
        "type": "snapshot", "meta": hub.meta(), "row_size": b.row_size,
        "bars": b.snapshot(200, ratio, stack), "book": hub.book.top(40),
        "profile": b.session_profile(), "tape": list(hub.tape)[-60:],
    })
    tick = 0
    try:
        while True:
            await asyncio.sleep(0.25)
            tick += 1
            new = hub.seq - seq
            seq = hub.seq
            msg = {"type": "update", "meta": hub.meta(), "book": hub.book.top(40),
                   "bars": b.snapshot(2, ratio, stack), "tape": list(hub.tape)[-min(new, 60):] if new else []}
            if tick % 8 == 0:
                msg["profile"] = b.session_profile()
            await ws.send_json(msg)
    except (WebSocketDisconnect, RuntimeError):
        return
