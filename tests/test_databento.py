"""DatabentoMerger against real databento_dbn record objects (no network / key needed)."""
import json
from datetime import date

import pytest

dbn = pytest.importorskip("databento_dbn")

from ofcore.feeds import DatabentoMerger  # noqa: E402

S = 1_000_000_000  # fixed-point scale
T0 = 1_791_000_000 * S


def trade(ts, px, size, side, seq):
    return dbn.TradeMsg(1, 42, ts, int(px * S), size, dbn.Action("T"), dbn.Side(side), 0, ts, dbn.F_LAST, 0, seq)


def mbp(ts, levels, action="A", side="N", px=0.0, size=0, seq=0, last=True):
    lv = [dbn.BidAskPair(int(b * S), int(a * S), bs, as_) for b, a, bs, as_ in levels]
    lv += [dbn.BidAskPair(dbn.UNDEF_PRICE, dbn.UNDEF_PRICE, 0, 0)] * (10 - len(lv))
    return dbn.MBP10Msg(1, 42, ts, int(px * S), size, dbn.Action(action), dbn.Side(side), 0, ts,
                        dbn.F_LAST if last else 0, 0, seq, lv)


@pytest.fixture
def m():
    trades, books = [], []
    mg = DatabentoMerger(lambda *a: trades.append(a), lambda *a: books.append(a))
    mg.trades, mg.books = trades, books
    return mg


def test_history_then_single_live_source(m):
    m.handle(trade(T0, 5800.0, 3, "B", 1))
    m.handle(trade(T0 + 1, 5799.75, 2, "A", 2))
    m.handle(mbp(T0 + 10, [(5799.75, 5800.0, 40, 35)]))
    m.handle(trade(T0 + 20, 5800.0, 1, "B", 3))  # live print on the trades stream: mbp owns it now
    m.handle(mbp(T0 + 20, [(5799.75, 5800.0, 40, 34)], action="T", side="B", px=5800.0, size=1, seq=3))
    assert [t[1:] for t in m.trades] == [(5800.0, 3.0, True), (5799.75, 2.0, False), (5800.0, 1.0, True)]
    assert m.stats["trades_hist"] == 2 and m.stats["trades_mbp"] == 1 and m.stats["ignored_trades_live"] == 1


def test_history_arriving_after_live_still_counts(m):
    """Replay and live can interleave: the cutoff is by event time, not arrival."""
    m.handle(mbp(T0 + 100, [(5800.0, 5800.25, 10, 10)]))
    m.handle(trade(T0 + 50, 5799.0, 4, "A", 9))  # earlier than the cutoff -> history, keep it
    assert m.trades == [(pytest.approx((T0 + 50) / S), 5799.0, 4.0, False)]
    assert m.stats["out_of_order"] == 0


def test_duplicate_print_skipped(m):
    m.handle(trade(T0 + 5, 5800.0, 2, "B", 7))
    m.handle(mbp(T0 + 5, [(5799.75, 5800.0, 1, 1)], action="T", side="B", px=5800.0, size=2, seq=7))
    assert len(m.trades) == 1 and m.stats["dup_skipped"] == 1


def test_book_is_full_top10_and_only_on_f_last(m):
    m.handle(mbp(T0, [(5799.75, 5800.0, 10, 12)], last=False))
    assert m.books == []  # mid-event: don't publish
    lv = [(5799.75 - i * 0.25, 5800.0 + i * 0.25, 10 + i, 20 + i) for i in range(10)]
    m.handle(mbp(T0 + 1, lv))
    bids, asks, snap = m.books[-1]
    assert snap is True and len(bids) == 10 and len(asks) == 10
    assert bids[0] == (5799.75, 10.0) and asks[0] == (5800.0, 20.0) and bids[-1][0] == 5797.5


def test_empty_levels_dropped_and_crossed_book_rejected(m):
    m.handle(mbp(T0, [(5799.75, 5800.0, 10, 12)]))
    assert len(m.books[-1][0]) == 1  # UNDEF levels removed
    m.handle(mbp(T0 + 1, [(5800.25, 5800.0, 5, 5)]))
    assert len(m.books) == 1 and m.stats["crossed"] == 1


def test_side_mapping_and_unknown(m):
    m.handle(trade(T0, 5800.0, 1, "A", 1))
    m.handle(trade(T0 + 1, 5800.0, 1, "N", 2))
    assert m.trades[0][3] is False and len(m.trades) == 1 and m.stats["unknown_side"] == 1


def test_mbp_non_trade_actions_are_not_prints(m):
    for a in ("A", "C", "M"):
        m.handle(mbp(T0, [(5799.75, 5800.0, 10, 12)], action=a, side="B", px=5800.0, size=5))
    assert m.trades == [] and m.stats["books"] == 3


def _session(records):
    class FakeLive:
        def __init__(self, key):
            self.subs = []

        def subscribe(self, **kw):
            self.subs.append(kw)

        def __iter__(self):
            return iter(records)

        def stop(self):
            pass

    return FakeLive


def test_verify_script_clean_and_dirty(monkeypatch, capsys, tmp_path):
    pytest.importorskip("databento")
    import time

    import databento

    from ofcore import verify_databento as vd

    now = time.time_ns() - 60 * S
    book = [(5799.75, 5800.0, 10, 12), (5799.5, 5800.25, 8, 9)]
    clean = [
        mbp(now, book),
        trade(now + 1, 5800.0, 2, "B", 11),
        mbp(now + 1, book, action="T", side="B", px=5800.0, size=2, seq=11),
        trade(now + 2, 5799.75, 1, "A", 12),
        mbp(now + 2, book, action="T", side="A", px=5799.75, size=1, seq=12),
    ]
    monkeypatch.setenv("DATABENTO_API_KEY", "x")
    monkeypatch.setattr(databento, "Live", _session(clean))
    assert vd.main(["ES", "--minutes", "2", "--report-dir", str(tmp_path)]) == 0
    assert "CLEAN" in capsys.readouterr().out
    rep = json.loads((tmp_path / "latest.json").read_text())["reports"][0]
    assert rep["status"] == "clean" and rep["records"]["mbp_prints_matched"] == 2

    dirty = clean + [
        mbp(now + 3, book, action="T", side="B", px=5800.0, size=5, seq=99),   # no matching trades record
        mbp(now + 4, [(5800.25, 5800.0, 1, 1)]),                                 # crossed
    ]
    monkeypatch.setattr(databento, "Live", _session(dirty))
    assert vd.main(["ES", "--minutes", "2", "--report-dir", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "mbp prints missing from trades" in out and "crossed" in out


def test_verify_without_key_writes_not_run_reports(monkeypatch, tmp_path, capsys):
    from ofcore import verify_databento as vd
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    assert vd.main(["--all", "--report-dir", str(tmp_path)]) == 3
    doc = json.loads((tmp_path / "latest.json").read_text())
    reps = {r["symbol"]: r for r in doc["reports"]}
    assert set(reps) == {"NQ", "MNQ", "ES", "MES"}
    for r in reps.values():
        assert r["status"] == "not_run" and r["reason"] == "DATABENTO_API_KEY unavailable"
        assert r["verified_at"] is None and r["checks"] == {} and "UNVERIFIED" in r["notes"][0]
    assert len(list(tmp_path.glob("20*.json"))) == 1


def test_expected_front_month_rolls_at_expiry():
    from ofcore.verify_databento import expected_front
    assert expected_front(date(2026, 9, 18), "NQ") == "NQU6"   # expiry day still September
    assert expected_front(date(2026, 9, 19), "NQ") == "NQZ6"
    assert expected_front(date(2026, 12, 20), "ES") == "ESH7"


def _raw(**counts):
    base = {"trades": 1000, "mbp": 50000, "books": 40000, "mbp_prints": 1000, "mbp_prints_matched": 1000}
    base.update(counts)
    return {"counts": base, "resolved": ["NQZ6"], "feed_symbol": "NQ.c.0"}


def test_evaluate_thresholds_and_mapping():
    from ofcore.verify_databento import evaluate
    d = date(2026, 10, 5)
    assert evaluate("NQ", 3, _raw(), d)["status"] == "clean"
    assert evaluate("NQ", 3, _raw(prints_inside_spread=3), d)["status"] == "clean"       # within tolerance
    assert evaluate("NQ", 3, _raw(prints_inside_spread=30), d)["status"] == "warning"
    assert evaluate("NQ", 3, _raw(mbp_prints_missing=50), d)["status"] == "failed"
    assert evaluate("NQ", 3, _raw(crossed_or_locked=1), d)["status"] == "warning"
    bad_map = _raw()
    bad_map["resolved"] = ["NQH7"]
    r = evaluate("NQ", 3, bad_map, d)
    assert r["status"] == "warning" and r["checks"]["contract_mapping"]["result"] == "mismatch"
    empty = evaluate("NQ", 3, {"counts": {}, "resolved": [], "feed_symbol": "NQ.c.0"}, d)
    assert empty["status"] == "failed"
