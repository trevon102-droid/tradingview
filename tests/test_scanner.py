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
