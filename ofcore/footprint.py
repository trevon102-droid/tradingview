"""Footprint (bid x ask per price per bar) + DOM book state, built from aggressor-tagged trades.

Every trade must say who was aggressive: is_buy=True means the buyer lifted the offer (counts on the
ASK side of the footprint), False means a seller hit the bid (BID side). Prices are kept as integer
row indexes (price // row_size) so float noise never splits a level.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import date

from .sessions import cme_session_bounds as session_bounds, cme_session_of as session_of  # noqa: F401


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
    first_ts: float = math.inf
    last_ts: float = -math.inf

    def add(self, row: int, price: float, size: float, is_buy: bool, ts: float) -> None:
        lv = self.levels.setdefault(row, [0.0, 0.0])
        lv[1 if is_buy else 0] += size
        self.high, self.low = max(self.high, price), min(self.low, price)
        # open/close follow trade time, not arrival order, so a late print can't overwrite them
        if ts < self.first_ts:
            self.first_ts, self.open = ts, price
        if ts >= self.last_ts:
            self.last_ts, self.close = ts, price
        # max/min delta assume arrival order; a late print shifts the path slightly (totals stay exact)
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
        # traded volume at price per CME session (for the DOM "traded" column + session profile),
        # keyed by session date -> tick row. Resets at 17:00 ET; a few past sessions kept for late prints.
        self.sessions: dict[date, dict[int, list[float]]] = {}
        self.keep_sessions = 3
        self._sess_cache: tuple[float, float, date] | None = None
        self.last: float | None = None
        self.last_ts = -math.inf

    def row(self, price: float) -> int:
        return math.floor(price / self.row_size + 1e-9)

    def on_trade(self, ts: float, price: float, size: float, is_buy: bool) -> bool:
        """Book one print. Returns True if it opened a new (latest) bar.

        Late prints (arriving after a newer bar opened) go into their own bar, which is created in
        order if that slot had no trades yet, and always count in the session profile. Prints older
        than the oldest kept bar only count in the session profile."""
        t = int(ts // self.bar_seconds * self.bar_seconds)
        new = not self.bars or t > self.bars[-1].t
        bar = None
        if new:
            bar = FPBar(t, price, price, price, price)
            self.bars.append(bar)
        elif t == self.bars[-1].t:
            bar = self.bars[-1]
        elif t >= self.bars[0].t:  # late print inside the kept window
            i = next(i for i in range(len(self.bars) - 1, -1, -1) if self.bars[i].t <= t)
            if self.bars[i].t == t:
                bar = self.bars[i]
            else:  # empty slot between bars: create it in time order
                bar = FPBar(t, price, price, price, price)
                if len(self.bars) == self.bars.maxlen:  # deque.insert raises when full: drop the oldest
                    self.bars.popleft()
                    i -= 1
                self.bars.insert(i + 1, bar)
        if bar is not None:
            bar.add(self.row(price), price, size, is_buy, ts)
        prof = self._session_for(ts)
        if prof is not None:
            s = prof.setdefault(math.floor(price / self.tick + 1e-9), [0.0, 0.0])
            s[1 if is_buy else 0] += size
        if ts >= self.last_ts:
            self.last_ts, self.last = ts, price
        return new

    def snapshot(self, n: int = 120, ratio: float = 3.0, stack: int = 3) -> list[dict]:
        return [analyze(b, self.row_size, ratio, stack=stack) for b in list(self.bars)[-n:]]

    def _session_for(self, ts: float) -> dict[int, list[float]] | None:
        c = self._sess_cache
        if c and c[0] <= ts < c[1]:
            d = c[2]
        else:
            d = session_of(ts)
            self._sess_cache = (*session_bounds(d), d)
        if d not in self.sessions:
            if self.sessions and d < min(self.sessions) and len(self.sessions) >= self.keep_sessions:
                return None  # print from a session we've already dropped
            self.sessions[d] = {}
            for old in sorted(self.sessions)[:-self.keep_sessions]:
                del self.sessions[old]
        return self.sessions[d]

    @property
    def session(self) -> date | None:
        """Current session = the one the latest print belongs to."""
        return session_of(self.last_ts) if self.last is not None else None

    def session_profile(self, d: date | None = None) -> list[list[float]]:
        """[price, bid_vol, ask_vol] for session `d` (default: current). Never mixes sessions."""
        d = d or self.session
        prof = self.sessions.get(d, {}) if d else {}
        return [[round(r * self.tick, 10), v[0], v[1]] for r, v in sorted(prof.items())]


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
