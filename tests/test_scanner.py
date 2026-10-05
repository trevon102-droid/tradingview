import json

import pytest

from ofcore import SYMBOLS, auction_read, get_bars
from ofcore.setups import Signal, detect
from scanner import scan as sc


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.setenv("OF_DATA", "demo")


def test_detect_returns_valid_signals():
    for key in ("ES", "NQ", "CL", "6E"):
        df = get_bars(key, "1h", 60)
        a = auction_read(df, SYMBOLS[key].tick)
        for s in detect(key, df, a, None):
            assert s.direction in {"long", "short", "info"} and s.symbol == key and s.text


def test_gamma_flip_cross_detected():
    df = get_bars("ES", "1h", 60)
    a = auction_read(df, 0.25)
    prev, last = float(df["close"].iloc[-2]), a["last"]
    g = {"zero_gamma": (prev + last) / 2 if prev != last else last + 0.125, "call_wall": None, "put_wall": None}
    codes = {s.code for s in detect("ES", df, a, g)}
    assert codes & {"gamma_flip_cross", "gamma_flip_near"}


def test_run_once_dedupes(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(sc, "notify", lambda sigs: sent.append(list(sigs)))
    cfg = sc.load_config(tmp_path / "missing.toml")
    cfg.update(symbols=["ES", "NQ", "CL", "GC", "6E", "EURUSD"], gamma=True, state_file=str(tmp_path / "s.json"))
    sc.run_once(cfg, dry=False)
    sc.run_once(cfg, dry=False)
    assert len(sent) == 2
    assert len(sent[0]) > 0, "demo tape should produce at least one setup"
    assert sent[1] == [], "second pass must not re-alert the same setups"
    assert json.loads((tmp_path / "s.json").read_text())


def test_chunks_respect_limit():
    body = "\n\n".join(["x" * 300] * 20)
    parts = list(sc._chunks(body, 1000))
    assert all(len(p) <= 1000 for p in parts) and "".join(parts).count("x") == 6000


def test_signal_key():
    s = Signal("ES", "accept_above", "long", "t", 1.0)
    assert s.key(1791200000) == "ES:accept_above:1791200000"


def test_setup_that_refires_same_day_is_a_new_event(monkeypatch):
    """Regression: accept -> fall back in -> accept again must give TWO alerts, not one per day."""
    from ofcore import setups

    df = get_bars("ES", "1h", 30)
    n = len(df)
    on_at = {n, n - 2}  # on at latest bar, off one bar earlier, on two bars earlier, off before that
    monkeypatch.setattr(setups, "auction_read", lambda sub, tick: {"n": len(sub)})
    monkeypatch.setattr(setups, "detect", lambda sym, sub, a, g, th: [Signal(sym, "accept_above", "long", "t", 1.0)]
                        if a["n"] in on_at else [])
    evs, _ = setups.events("ES", df, 0.25, lookback=3)
    keys = sorted(k for k, _ in evs)
    assert len(keys) == 2 and len(set(keys)) == 2
    assert {int(k.rsplit(":", 1)[1]) for k in keys} == {int(df.index[-1].timestamp()), int(df.index[-3].timestamp())}

    # setup that just stays on doesn't re-alert
    monkeypatch.setattr(setups, "detect", lambda sym, sub, a, g, th: [Signal(sym, "accept_above", "long", "t", 1.0)])
    assert setups.events("ES", df, 0.25, lookback=3)[0] == []


def test_closed_bars_drops_forming_candle():
    import pandas as pd

    from ofcore.setups import closed_bars

    df = get_bars("ES", "1h", 5)
    last = df.index[-1]
    assert len(closed_bars(df, pd.Timedelta(hours=1), now=last + pd.Timedelta(minutes=30))) == len(df) - 1
    assert len(closed_bars(df, pd.Timedelta(hours=1), now=last + pd.Timedelta(hours=1))) == len(df)


# ---------- gamma must never be evaluated on historical bars ----------

def _window_where(df, pred, need=60):
    """Smallest-tail cut of df (>= need bars) whose last closes satisfy pred(closes)."""
    for end in range(len(df), need, -1):
        sub = df.iloc[:end]
        if pred(sub["close"].to_numpy()):
            return sub
    raise AssertionError("no matching window in demo tape")


def test_gamma_cross_on_old_bar_is_not_an_event():
    """Regression: a flip level from TODAY's chain crossed by price 3 bars ago must not alert."""
    from ofcore import setups

    df = get_bars("ES", "1h", 60)

    def pred(c):  # ONLY bar -3 crossed a level between c[-4] and c[-3]; bars before/after stay on their sides
        zg = (c[-4] + c[-3]) / 2
        return (abs(c[-4] - c[-3]) >= 4 and (c[-5] - zg) * (c[-4] - zg) > 0
                and all(abs(x - zg) > 15 and (x - zg) * (c[-3] - zg) > 0 for x in c[-2:]))
    sub = _window_where(df, pred)
    c = sub["close"].to_numpy()
    g = {"zero_gamma": (c[-4] + c[-3]) / 2, "call_wall": None, "put_wall": None}
    evs, _ = setups.events("ES", sub, 0.25, g, setups.Thresholds(gamma_atr=0.01), lookback=3)
    assert not [k for k, s in evs if s.code.startswith("gamma")], evs


def test_gamma_cross_on_latest_bar_is_one_event_keyed_to_that_bar():
    from ofcore import setups

    df = get_bars("ES", "1h", 60)
    sub = _window_where(df, lambda c: abs(c[-2] - c[-1]) >= 2)
    c = sub["close"].to_numpy()
    g = {"zero_gamma": (c[-2] + c[-1]) / 2, "call_wall": None, "put_wall": None}
    evs, _ = setups.events("ES", sub, 0.25, g, lookback=3)
    gam = [k for k, s in evs if s.code.startswith("gamma")]
    assert gam == [f"ES:gamma_flip_cross:{int(sub.index[-1].timestamp())}"]


def test_history_replay_never_sees_gamma(monkeypatch):
    from ofcore import setups

    seen = []
    real = setups.detect
    monkeypatch.setattr(setups, "detect", lambda sym, sub, a, g, th: (seen.append(g), real(sym, sub, a, g, th))[1])
    setups.events("ES", get_bars("ES", "1h", 30), 0.25, {"zero_gamma": 1.0}, lookback=3)
    assert len(seen) == 4 and all(g is None for g in seen)


def test_gamma_state_keyed_by_level_not_bar():
    """'Near flip' can't be diffed against history, so it alerts once per level, not every bar."""
    from ofcore import setups

    df = get_bars("ES", "1h", 60)
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    lvl = last + (0.25 if last >= prev else -0.25)  # right next to price, not crossed this bar
    g = {"zero_gamma": lvl, "call_wall": None, "put_wall": None}
    k1 = [k for k, s in setups.events("ES", df, 0.25, g)[0] if s.code == "gamma_flip_near"]
    assert k1 == [f"ES:gamma_flip_near:lvl={lvl:g}"]  # no bar time in the key
    g2 = {**g, "zero_gamma": lvl + 0.25}
    k3 = [k for k, s in setups.events("ES", df, 0.25, g2)[0] if s.code == "gamma_flip_near"]
    assert k3 and k3 != k1  # options data moved the level -> new alert


def test_live_event_log_is_point_in_time(tmp_path, monkeypatch):
    import json

    import research.records as rec
    from ofcore import SYMBOLS, auction_read
    from ofcore.setups import events
    from scanner.scan import log_live_events

    monkeypatch.setattr(rec, "EVENTS_DIR", tmp_path)
    df = get_bars("ES", "1h", 30)
    g = {"zero_gamma": float(df["close"].iloc[-1]) + 1000, "call_wall": None, "put_wall": None, "regime": "negative",
         "proxy": "SPY", "calculated_at": "2026-10-05T14:00:00+00:00", "source": "test"}
    evs, a = events("ES", df, 0.25, g, lookback=3)
    sigs = [s for _, s in evs]
    assert sigs
    log_live_events("ES", "1h", df, a, sigs, g, SYMBOLS["ES"].tick)
    log_live_events("ES", "1h", df, a, sigs, g, SYMBOLS["ES"].tick)   # idempotent
    rows = [json.loads(x) for f in tmp_path.glob("live/*.jsonl") for x in f.read_text().splitlines()]
    assert len(rows) == len({r["event_id"] for r in rows}) == len(sigs)
    last_bar = int(df.index[-1].timestamp())
    pos = {int(t.timestamp()): i for i, t in enumerate(df.index)}
    for r in rows:
        assert r["source"] == "live:scanner" and r["data_quality"]["delta"] == "estimated"
        if r["bar_open"] == last_bar:
            assert r["data_quality"]["gamma"] == "estimated" and r["context"]["gamma"]["proxy"] == "SPY"
        else:   # lookback-bar events: no gamma, and the auction read of data ending at their own bar
            assert r["data_quality"]["gamma"] == "unavailable" and r["context"]["gamma_regime"] is None
            own = auction_read(df.iloc[:pos[r["bar_open"]] + 1], 0.25)
            assert r["context"]["auction_read"] == own["read"] and r["context"]["auction_state"] == own["state"]
