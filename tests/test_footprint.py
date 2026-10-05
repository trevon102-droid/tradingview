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


def test_late_print_updates_session_profile_and_keeps_close():
    """Regression: late prints must land in their bar AND the session profile, without moving close/last."""
    b = build([(10, 100.0, 1, True), (20, 100.5, 1, True), (70, 101.0, 2, True), (15, 99.0, 4, False)])
    first = b.bars[0]
    assert first.volume == 6 and first.low == 99.0
    assert first.close == 100.5, "late print at t=15 must not become the close of a bar that traded at t=20"
    assert first.open == 100.0
    assert b.last == 101.0
    sess = {p: v for p, *v in b.session_profile()}
    assert sess[99.0] == [4, 0], "late print missing from session profile"
    assert sum(v[0] + v[1] for v in sess.values()) == sum(x.volume for x in b.bars)


def test_late_print_earlier_than_first_trade_becomes_open():
    b = build([(30, 100.0, 1, True), (70, 101.0, 1, True), (5, 98.0, 1, False)])
    assert b.bars[0].open == 98.0 and b.bars[0].close == 100.0


def test_late_print_into_empty_slot_is_inserted_in_order():
    b = build([(10, 100.0, 1, True), (130, 102.0, 1, True), (70, 101.0, 3, False)])
    assert [x.t for x in b.bars] == [0, 60, 120]
    assert b.bars[1].volume == 3 and b.last == 102.0


def test_late_print_into_empty_slot_when_full_does_not_crash():
    b = FootprintBuilder(0.25, 60, 1, keep=3)
    for ts in (10, 130, 190):
        b.on_trade(ts, 100.0, 1, True)
    b.on_trade(70, 99.0, 1, False)  # slot 60 is empty and the deque is full
    assert [x.t for x in b.bars] == [60, 120, 180]
    assert len(b.bars) == 3


def test_print_older_than_window_still_counts_in_session():
    b = FootprintBuilder(0.25, 60, 1, keep=2)
    for ts in (10, 70, 130):
        b.on_trade(ts, 100.0, 1, True)
    b.on_trade(5, 97.0, 2, False)
    assert [x.t for x in b.bars] == [60, 120]
    assert {p: v for p, *v in b.session_profile()}[97.0] == [2, 0]


# ---------- session profile resets at the CME session boundary ----------
from datetime import date, datetime  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

_ET = ZoneInfo("America/New_York")


def et(*a) -> float:
    return datetime(*a, tzinfo=_ET).timestamp()


def vol(profile) -> float:
    return sum(b + a for _, b, a in profile)


def test_two_sessions_never_share_profile_volume():
    b = FootprintBuilder(0.25, 300, 1)
    b.on_trade(et(2026, 10, 5, 16, 59), 5800.0, 7, True)    # last minute of Monday's session
    b.on_trade(et(2026, 10, 5, 18, 1), 5801.0, 3, False)    # Globex reopen -> Tuesday's session
    assert b.session == date(2026, 10, 6)
    assert b.session_profile() == [[5801.0, 3, 0]]           # current session: only post-reopen volume
    assert b.session_profile(date(2026, 10, 5)) == [[5800.0, 0, 7]]
    assert vol(b.session_profile()) + vol(b.session_profile(date(2026, 10, 5))) == 10


def test_session_spans_midnight_and_overnight():
    b = FootprintBuilder(0.25, 300, 1)
    for ts in (et(2026, 10, 5, 18, 0), et(2026, 10, 5, 23, 30), et(2026, 10, 6, 3, 0), et(2026, 10, 6, 16, 59, 59)):
        b.on_trade(ts, 5800.0, 1, True)
    assert b.session == date(2026, 10, 6) and vol(b.session_profile()) == 4 and len(b.sessions) == 1


def test_exact_roll_boundary():
    b = FootprintBuilder(0.25, 300, 1)
    b.on_trade(et(2026, 10, 6, 16, 59, 59) + 0.999, 5800.0, 1, True)
    b.on_trade(et(2026, 10, 6, 17, 0, 0), 5800.0, 2, True)   # 17:00:00 belongs to the next session
    assert vol(b.session_profile(date(2026, 10, 6))) == 1 and vol(b.session_profile(date(2026, 10, 7))) == 2


def test_sunday_open_is_mondays_session_and_friday_is_separate():
    b = FootprintBuilder(0.25, 300, 1)
    b.on_trade(et(2026, 10, 2, 16, 0), 5790.0, 5, False)    # Friday afternoon
    b.on_trade(et(2026, 10, 4, 18, 0), 5795.0, 4, True)     # Sunday 18:00 open
    assert b.session == date(2026, 10, 5)
    assert b.session_profile() == [[5795.0, 0, 4]]
    assert b.session_profile(date(2026, 10, 2)) == [[5790.0, 5, 0]]


def test_session_roll_across_dst_change():
    # US DST ends Sun Nov 1 2026: Friday closes on EDT, Sunday reopens on EST
    b = FootprintBuilder(0.25, 300, 1)
    b.on_trade(et(2026, 10, 30, 16, 30), 5800.0, 2, True)
    b.on_trade(et(2026, 11, 1, 18, 0), 5810.0, 3, True)
    b.on_trade(et(2026, 11, 2, 16, 59), 5812.0, 1, True)
    b.on_trade(et(2026, 11, 2, 17, 0), 5813.0, 6, True)
    assert vol(b.session_profile(date(2026, 10, 30))) == 2
    assert vol(b.session_profile(date(2026, 11, 2))) == 4
    assert vol(b.session_profile(date(2026, 11, 3))) == 6


def test_late_print_from_previous_session_stays_in_that_session():
    b = FootprintBuilder(0.25, 300, 1)
    b.on_trade(et(2026, 10, 5, 16, 58), 5800.0, 1, True)
    b.on_trade(et(2026, 10, 5, 18, 0), 5802.0, 1, True)      # new session started
    b.on_trade(et(2026, 10, 5, 16, 59), 5799.0, 9, False)    # late print from the old session
    assert b.session == date(2026, 10, 6)
    assert vol(b.session_profile()) == 1, "late print leaked into the new session's profile"
    assert vol(b.session_profile(date(2026, 10, 5))) == 10


def test_old_sessions_are_dropped():
    b = FootprintBuilder(0.25, 300, 1)
    for d in range(5, 10):
        b.on_trade(et(2026, 10, d, 10, 0), 5800.0, 1, True)
    assert sorted(b.sessions) == [date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)]
    b.on_trade(et(2026, 10, 5, 11, 0), 5800.0, 1, True)       # print from a dropped session: ignored
    assert sorted(b.sessions) == [date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)]
