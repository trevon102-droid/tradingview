"""Footprint (bid x ask per price per bar) + DOM book state, built from aggressor-tagged trades.

Every trade must say who was aggressive: is_buy=True means the buyer lifted the offer (counts on the
ASK side of the footprint), False means a seller hit the bid (BID side). Prices are kept as integer
row indexes (price // row_size) so float noise never splits a level.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field


@dataclass
class FPBar:
    t: int  # bar open, unix seconds
    open: float
    high: float
    low: float
    close: float
    levels: dict[int, list[float]] = field(default_factory=dict)  # row -> [bid_vol, ask_vol]
    delta: float = 0.0
    max_delta: float = 0.0
    min_delta: float = 0.0
    volume: float = 0.0
    trades: int = 0

    def add(self, row: int, price: float, size: float, is_buy: bool) -> None:
        lv = self.levels.setdefault(row, [0.0, 0.0])
        lv[1 if is_buy else 0] += size
        self.high, self.low, self.close = max(self.high, price), min(self.low, price), price
        self.delta += size if is_buy else -size
        self.max_delta, self.min_delta = max(self.max_delta, self.delta), min(self.min_delta, self.delta)
        self.volume += size
        self.trades += 1


def analyze(bar: FPBar, row_size: float, ratio: float = 3.0, min_vol: float = 0.0, stack: int = 3) -> dict:
    """Serialize a bar with diagonal imbalances, POC, stacked imbalance zones and unfinished auctions."""
    rows = sorted(bar.levels)
    bid = {r: bar.levels[r][0] for r in rows}
    ask = {r: bar.levels[r][1] for r in rows}
    cells, buy_imb, sell_imb = [], set(), set()
    nz = sorted(v for r in rows for v in (bid[r], ask[r]) if v > 0)
    floor = max(min_vol, nz[len(nz) // 2] if nz else 0.0)  # x-vs-zero only counts if x is a real print
    lo_r, hi_r = (rows[0], rows[-1]) if rows else (0, 0)
    for r in rows:
        # diagonal: buyers at r vs sellers one row below; sellers at r vs buyers one row above.
        # Nothing to compare against beyond the bar's extremes, so those edges never flag.
        b_under, a_over = bid.get(r - 1, 0.0), ask.get(r + 1, 0.0)
        if r > lo_r and ask[r] > min_vol and (ask[r] >= ratio * b_under if b_under > 0 else ask[r] >= floor):
            buy_imb.add(r)
        if r < hi_r and bid[r] > min_vol and (bid[r] >= ratio * a_over if a_over > 0 else bid[r] >= floor):
            sell_imb.add(r)
    poc = max(rows, key=lambda r: bid[r] + ask[r]) if rows else None
    for r in rows:
        cells.append([_px(r, row_size), bid[r], ask[r], 1 if r in buy_imb else -1 if r in sell_imb else 0])
    hi, lo = (rows[-1], rows[0]) if rows else (None, None)
    return {
        "t": bar.t, "o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close,
        "cells": cells, "poc": _px(poc, row_size) if poc is not None else None,
        "delta": bar.delta, "max_delta": bar.max_delta, "min_delta": bar.min_delta,
        "volume": bar.volume, "trades": bar.trades,
        "stacked_buy": _runs(sorted(buy_imb), stack, row_size),
        "stacked_sell": _runs(sorted(sell_imb), stack, row_size),
        # both sides traded at the extreme = auction didn't finish there, market tends to come back
        "unfinished_high": bool(rows and bid[hi] > 0 and ask[hi] > 0),
        "unfinished_low": bool(rows and bid[lo] > 0 and ask[lo] > 0),
    }


def _px(row: int, row_size: float) -> float:
    return round(row * row_size, 10)


def _runs(rows: list[int], n: int, row_size: float) -> list[list[float]]:
    """Consecutive rows (len >= n) as [low_px, high_px + row] zones."""
    out, start = [], None
    for i, r in enumerate(rows):
        if start is None:
            start = r
        if i == len(rows) - 1 or rows[i + 1] != r + 1:
            if r - start + 1 >= n:
                out.append([_px(start, row_size), _px(r + 1, row_size)])
            start = None
    return out


class FootprintBuilder:
    def __init__(self, tick: float, bar_seconds: int = 300, row_ticks: int = 1, keep: int = 300):
        self.tick, self.bar_seconds, self.row_ticks = tick, bar_seconds, row_ticks
        self.row_size = tick * row_ticks
        self.bars: deque[FPBar] = deque(maxlen=keep)
        # session traded volume at price (for the DOM "traded" column), keyed by tick row
        self.session: dict[int, list[float]] = {}
        self.last: float | None = None

    def row(self, price: float) -> int:
        return math.floor(price / self.row_size + 1e-9)

    def on_trade(self, ts: float, price: float, size: float, is_buy: bool) -> bool:
        """Returns True if this trade opened a new bar."""
        t = int(ts // self.bar_seconds * self.bar_seconds)
        new = not self.bars or t > self.bars[-1].t
        if new:
            self.bars.append(FPBar(t, price, price, price, price))
        elif t < self.bars[-1].t:  # late print from an earlier bar: book it there if we still have it
            for b in reversed(self.bars):
                if b.t == t:
                    b.add(self.row(price), price, size, is_buy)
                    break
            return False
        self.bars[-1].add(self.row(price), price, size, is_buy)
        s = self.session.setdefault(math.floor(price / self.tick + 1e-9), [0.0, 0.0])
        s[1 if is_buy else 0] += size
        self.last = price
        return new

    def snapshot(self, n: int = 120, ratio: float = 3.0, stack: int = 3) -> list[dict]:
        return [analyze(b, self.row_size, ratio, stack=stack) for b in list(self.bars)[-n:]]

    def session_profile(self) -> list[list[float]]:
        return [[round(r * self.tick, 10), v[0], v[1]] for r, v in sorted(self.session.items())]


class Book:
    """Price -> size for each side. Feeds push snapshots or level updates; size 0 deletes a level."""

    def __init__(self):
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}

    def reset(self):
        self.bids.clear()
        self.asks.clear()

    def set(self, side: str, price: float, size: float):
        book = self.bids if side == "bid" else self.asks
        if size <= 0:
            book.pop(price, None)
        else:
            book[price] = size

    def top(self, n: int = 40) -> dict:
        bids = sorted(self.bids.items(), reverse=True)[:n]
        asks = sorted(self.asks.items())[:n]
        return {"bids": bids, "asks": asks}
