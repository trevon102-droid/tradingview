import pytest

from ofcore.feeds import FP_SYMBOLS, SimFeed
from ofcore.footprint import Book, FootprintBuilder, analyze


def build(trades, bar=60, tick=0.25, row=1):
    b = FootprintBuilder(tick, bar, row)
    for t in trades:
        b.on_trade(*t)
    return b


def test_bid_ask_split_and_delta():
    b = build([(0, 100.0, 5, True), (1, 100.0, 2, False), (2, 100.25, 3, True)])
    bar = b.bars[-1]
    assert bar.levels[b.row(100.0)] == [2, 5]
    assert bar.delta == 6 and bar.volume == 10 and bar.max_delta == 6 and bar.min_delta == 0
    assert (bar.open, bar.high, bar.low, bar.close) == (100.0, 100.25, 100.0, 100.25)


def test_bars_roll_and_late_prints_go_to_their_bar():
    b = build([(10, 100, 1, True), (70, 101, 1, True), (50, 99, 4, False)])
    assert [x.t for x in b.bars] == [0, 60]
    assert b.bars[0].volume == 5 and b.bars[0].low == 99


def test_diagonal_imbalance_and_stacks():
    # sellers small one row below each ask print -> buy imbalances stacked on 3 rows
    tr = []
    for i, px in enumerate([100.0, 100.25, 100.5, 100.75]):
        tr.append((i, px, 2, False))   # bid side at px
        tr.append((i, px, 10, True))   # ask side at px
    a = analyze(build(tr).bars[-1], 0.25, ratio=3, stack=3)
    imb = {c[0]: c[3] for c in a["cells"]}
    # ask@100.25 (10) vs bid@100.0 (2) -> 5x, and so on upward; the lowest row has nothing below it
    assert imb[100.25] == imb[100.5] == imb[100.75] == 1
    assert a["stacked_buy"] == [[100.25, 101.0]]
    assert a["stacked_sell"] == []
    assert a["unfinished_high"] and a["unfinished_low"]


def test_no_imbalance_when_balanced():
    tr = [(0, 100.0, 5, False), (0, 100.0, 5, True), (1, 100.25, 5, False), (1, 100.25, 5, True)]
    a = analyze(build(tr).bars[-1], 0.25)
    assert all(c[3] == 0 for c in a["cells"])
    assert a["poc"] in (100.0, 100.25)


def test_row_grouping():
    b = build([(0, 100.0, 1, True), (0, 100.75, 1, True), (0, 101.0, 1, False)], row=4)
    rows = sorted(b.bars[-1].levels)
    assert len(rows) == 2  # 100.00-100.75 share a 1-point row, 101.00 is the next


def test_book_updates():
    bk = Book()
    bk.set("bid", 99.75, 10)
    bk.set("bid", 99.5, 5)
    bk.set("ask", 100.0, 7)
    bk.set("bid", 99.75, 0)
    top = bk.top(5)
    assert top["bids"] == [(99.5, 5)] and top["asks"] == [(100.0, 7)]


@pytest.mark.parametrize("key", ["ES", "NQ", "BTC"])
def test_sim_feed_is_sane(key):
    sym = FP_SYMBOLS[key]
    sim = SimFeed(sym, seed=1, backfill_min=30)
    b = FootprintBuilder(sym.tick, 300, sym.row_ticks)
    sim.backfill(b.on_trade, now=10_000_000)
    assert 5 <= len(b.bars) <= 8
    for bar in b.bars:
        assert bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high
        assert abs(bar.high - bar.low) < sym.sim_price * 0.02
    bids, asks = sim._book()
    assert max(p for p, _ in bids) < min(p for p, _ in asks)


def test_websocket_streams_sim(monkeypatch):
    from fastapi.testclient import TestClient

    from dashboard.app import app

    with TestClient(app) as c, c.websocket_connect("/ws/footprint?sym=ES&mode=sim&bar=300") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot" and snap["meta"]["feed"] == "sim" and snap["meta"]["live"] is False
        assert len(snap["bars"]) > 10 and snap["book"]["bids"] and snap["profile"]
        upd = ws.receive_json()
        assert upd["type"] == "update" and len(upd["bars"]) <= 2


def test_kraken_message_parsing():
    from ofcore.feeds import KrakenFeed, _side

    trades, books = [], []
    on_t = lambda *a: trades.append(a)  # noqa: E731
    on_b = lambda *a: books.append(a)  # noqa: E731
    KrakenFeed.handle({"channel": "trade", "type": "update", "data": [
        {"symbol": "BTC/USD", "side": "sell", "price": 98000.1, "qty": 0.25, "ord_type": "market",
         "trade_id": 1, "timestamp": "2026-10-05T14:30:00.500000Z"}]}, on_t, on_b)
    KrakenFeed.handle({"channel": "book", "type": "snapshot", "data": [
        {"symbol": "BTC/USD", "bids": [{"price": 98000.0, "qty": 1.5}], "asks": [{"price": 98000.2, "qty": 0.7}],
         "checksum": 1}]}, on_t, on_b)
    KrakenFeed.handle({"channel": "heartbeat"}, on_t, on_b)
    assert trades == [(1791210600.5, 98000.1, 0.25, False)]
    assert books == [([(98000.0, 1.5)], [(98000.2, 0.7)], True)]
    assert _side("B") == "B" and _side(65) == "A"
