"""Research pipeline: point-in-time integrity, forward outcomes, gating, data-quality propagation.

The leakage tests try to break the pipeline on purpose: if changing or appending FUTURE bars changes any
past event or its context, something is looking ahead.
"""
import json
import math

import numpy as np
import pandas as pd
import pytest

from ofcore import get_bars
from research.outcomes import Series, outcome
from research.records import EventRecord, make_id
from research.replay import causal_context, replay
from research.study import (COMBOS, MIN_N, attach_baseline, cluster_boot, event_frame, status_for, study_group,
                            summarize, wilson)


@pytest.fixture(scope="module")
def nq():
    df = get_bars("NQ", "1h", 120, provider="demo")
    df["price_bad"] = False
    df["volume_bad"] = False
    return df


def _events(df, start, end):
    return {e.event_id: e.to_json() for e in replay("NQ", "1h", df, 0.25, "t", start=start, end=end)}


# ---------------------------------------------------------------- leakage

def test_appending_future_bars_never_changes_past_events(nq):
    n = len(nq)
    cut = n - 40
    past = _events(nq.iloc[:cut], cut - 60, cut)
    full = _events(nq, cut - 60, cut)
    assert past and past == full


def test_perturbing_future_bars_never_changes_past_events(nq):
    n = len(nq)
    cut = n - 40
    bent = nq.copy()
    for c in ("open", "high", "low", "close"):
        bent.iloc[cut:, bent.columns.get_loc(c)] *= 1.5          # wildly different future
    bent.iloc[cut:, bent.columns.get_loc("volume")] *= 20
    assert _events(nq, cut - 60, cut) == _events(bent, cut - 60, cut)


def test_every_event_is_reproducible_from_data_ending_at_its_own_bar(nq):
    """The strict point-in-time check: cut the data at the event bar itself and re-run. The record must
    come out byte-identical, so nothing in it can depend on any later bar."""
    evs = replay("NQ", "1h", nq, 0.25, "t", start=len(nq) - 120, end=len(nq) - 20)
    assert len(evs) >= 10
    pos = {int(t.timestamp()): i for i, t in enumerate(nq.index)}
    for e in evs[:25]:
        i = pos[e.bar_open]
        again = {x.event_id: x.to_json() for x in replay("NQ", "1h", nq.iloc[:i + 1], 0.25, "t", start=i, end=i + 1)}
        assert again.get(e.event_id) == e.to_json(), e.event


def test_causal_context_equals_truncated_recompute(nq):
    base = nq[["open", "high", "low", "close", "volume"]]
    full = causal_context(base, 3600)
    for i in (900, 1500, len(base) - 5):
        part = causal_context(base.iloc[:i + 1], 3600)
        a, b = full.iloc[i], part.iloc[-1]
        for k in full.columns:
            if isinstance(a[k], float) and not math.isnan(a[k]):
                assert a[k] == pytest.approx(b[k], rel=1e-9), k
            else:
                assert (a[k] == b[k]) or (pd.isna(a[k]) and pd.isna(b[k])), k


def test_event_records_hold_no_outcomes_and_no_gamma(nq):
    evs = replay("NQ", "1h", nq, 0.25, "t", start=len(nq) - 80)
    assert evs
    for e in evs:
        blob = json.loads(e.to_json())
        flat = json.dumps(blob)
        assert not any(k in flat for k in ("fwd_", "mfe", "mae", "outcome"))
        assert blob["context"]["gamma_regime"] is None and blob["data_quality"]["gamma"] == "unavailable"
        assert blob["data_quality"]["delta"] == "estimated"
        assert pd.Timestamp(blob["timestamp"]).timestamp() == blob["bar_open"] + 3600  # known at bar close


def test_event_session_label_is_judged_at_bar_close(nq):
    from ofcore.sessions import session_label
    for e in replay("NQ", "1h", nq, 0.25, "t", start=len(nq) - 80):
        assert e.session == session_label(e.bar_open + 3599)


def test_degraded_price_propagates_to_event(nq):
    bad = nq.copy()
    bad["price_bad"] = True
    evs = replay("NQ", "1h", bad, 0.25, "t", start=len(nq) - 40)
    assert evs and all(e.data_quality["price"] == "degraded" for e in evs)


# ---------------------------------------------------------------- forward outcomes

def _series(prices, highs=None, lows=None, res=60, t0=0, bad=None):
    n = len(prices)
    t = np.arange(n, dtype=np.int64) * res + t0
    p = np.asarray(prices, float)
    return Series(res, t, np.asarray(highs if highs is not None else p, float),
                  np.asarray(lows if lows is not None else p, float), p,
                  np.zeros(n, bool) if bad is None else np.asarray(bad))


def test_outcome_uses_only_bars_after_signal():
    # bars before T are wild; they must not matter. Entry 100 at T=600 (bar 10 opens at 600).
    prices = [500] * 10 + [101, 102, 99, 103, 104] + [100] * 10
    highs = [900] * 10 + [101.5, 102.5, 99.5, 103.5, 104.5] + [100] * 10
    lows = [1] * 10 + [100.5, 101.5, 98.5, 102.5, 103.5] + [100] * 10
    s = _series(prices, highs, lows)
    o = outcome([s], T=600, entry=100.0, H=300, atr=2.0)   # 5 one-minute bars: indices 10..14
    assert o["status"] == "ok" and o["bars"] == 5
    assert o["fwd_pts"] == pytest.approx(4.0)               # close of bar 14 (104) - entry
    assert o["mfe_pts"] == pytest.approx(4.5)               # max high 104.5
    assert o["mae_pts"] == pytest.approx(1.5)               # min low 98.5
    assert o["t_up_min"] == pytest.approx(1.0)              # +1.0 (0.5 ATR) reached by end of first bar
    assert o["t_dn_min"] == pytest.approx(3.0)              # -1.0 reached by end of third bar


def test_outcome_short_horizon_needs_fine_resolution():
    coarse = _series([100] * 50, res=3600)
    assert outcome([coarse], T=3600, entry=100, H=300, atr=1)["status"] == "unavailable"


def test_outcome_with_gap_or_degraded_price_is_excluded():
    gap = _series([100.0] * 3, t0=600)     # only 3 of 5 bars after T=600
    assert outcome([gap], T=600, entry=100, H=300, atr=1)["status"] == "unavailable"
    bad = np.zeros(30, bool)
    bad[12] = True
    s = _series([100.0] * 30, bad=bad)
    assert outcome([s], T=600, entry=100, H=300, atr=1)["status"] == "degraded_price"


def test_outcome_falls_back_to_coarser_resolution():
    fine = _series([100.0] * 5, res=60, t0=0)            # 1m only covers the first 5 minutes
    coarse = _series(list(np.linspace(100, 110, 40)), res=300, t0=0)
    o = outcome([fine, coarse], T=600, entry=100, H=3600, atr=1)
    assert o["status"] == "ok" and o["res"] == 300


# ---------------------------------------------------------------- study: signs, baseline, gating

def _fake(n, hit, sign=1, sym="NQ", tf="5m", hz=30, start="2026-08-03"):
    ts = pd.date_range(start, periods=n, freq="7h", tz="UTC")
    ev = [{"event_id": f"e{i}", "timestamp": t.isoformat(), "symbol": sym, "timeframe": tf, "event": "x",
           "session": "RTH", "direction": "long" if sign > 0 else "short", "hypothesis": None,
           "price": 100.0, "level": None, "context": {"regime": "trend", "vs_rth_vwap": "above",
                                                       "vs_weekly_vwap": "above", "rvol_bucket": "high",
                                                       "ema_stack": "bull", "gamma_regime": None,
                                                       "bar_direction": "up"},
           "data_quality": {"price": "clean", "delta": "estimated", "gamma": "unavailable", "volume": "clean"}}
          for i, t in enumerate(ts)]
    rng = np.random.default_rng(1)
    good = rng.random(n) < hit
    fwd = np.where(good, 2.0, -2.0) * sign
    out = pd.DataFrame({"event_id": [f"e{i}" for i in range(n)], "horizon": hz, "atr": 2.0, "status": "ok",
                        "res": 60, "fwd_pts": fwd, "mfe_pts": np.abs(fwd), "mae_pts": 0.5,
                        "t_up_min": 3.0, "t_dn_min": None})
    bt = pd.DataFrame([{"symbol": sym, "timeframe": tf, "session": "RTH", "horizon": hz,
                        "p_up": 0.5, "p_dn": 0.5, "mean_r_long": 0.0, "n_bars": 10000}])
    return attach_baseline(event_frame(ev, out), bt)


def test_small_sample_is_never_promoted():
    df = _fake(8, hit=1.0)                    # 100% hit rate on 8 events
    res = study_group(df, "5m")
    assert res["status"] == "INSUFFICIENT_SAMPLE" and res["primary"]["n"] == 8


def test_strong_consistent_signal_is_promising_and_short_sign_applies():
    for sign in (1, -1):
        res = study_group(_fake(200, hit=0.75, sign=sign), "5m")
        assert res["status"] == "PROMISING", res["why"]
        assert res["primary"]["edge_r"] > 0          # a short that works counts as positive


def test_coin_flip_is_weak_and_wrong_way_is_invalidated():
    assert study_group(_fake(300, hit=0.5), "5m")["status"] in ("WEAK", "MIXED")
    assert study_group(_fake(300, hit=0.2), "5m")["status"] == "INVALIDATED"


def test_info_event_hypothesis_sign():
    ev = _fake(40, hit=0.6)
    assert set(ev["sign"]) == {1}
    from research.study import _sign
    assert _sign({"direction": "info", "hypothesis": "toward_level", "level": 110, "price": 100,
                  "bar_direction": "up"}) == 1
    assert _sign({"direction": "info", "hypothesis": "toward_level", "level": 90, "price": 100,
                  "bar_direction": "up"}) == -1
    assert _sign({"direction": "info", "hypothesis": "with_bar", "level": None, "price": 100,
                  "bar_direction": "down"}) == -1
    assert _sign({"direction": "info", "hypothesis": None, "level": None, "price": 100,
                  "bar_direction": "up"}) == 0


def test_degraded_outcomes_are_excluded_from_stats():
    df = _fake(60, hit=0.6)
    df.loc[df.index[:20], "status"] = "degraded_price"
    assert summarize(df)["n"] == 40


def test_combo_filters_and_gamma_combo_untestable():
    assert any(c.get("untestable") for c in COMBOS)
    df = _fake(100, hit=0.6)
    df.loc[df.index[:70], "ema_stack"] = "bear"
    c = next(c for c in COMBOS if c["event"] == "cvd_div_bullish")
    g = df.copy()
    for k, v in c["filters"].items():
        g = g[g[k] == v]
    assert len(g) == 30


def test_stats_helpers():
    lo, hi = wilson(8, 10)
    assert 0.44 < lo < 0.5 and 0.94 < hi < 0.98
    v = np.r_[np.ones(50), -np.ones(50)]
    ci = cluster_boot(v, np.repeat(np.arange(10), 10))
    assert ci[0] < 0 < ci[1]
    assert status_for({"n": MIN_N - 1}, {}, {})[0] == "INSUFFICIENT_SAMPLE"


def test_event_ids_are_stable_and_unique():
    a = make_id("s", "NQ", "5m", "rvol", 100)
    assert a == make_id("s", "NQ", "5m", "rvol", 100) and a != make_id("s", "NQ", "5m", "rvol", 400)
    r = EventRecord(a, "t", 1, "NQ", "5m", "RTH", "rvol", "info", "with_bar", 1.0, None)
    assert json.loads(r.to_json())["event_id"] == a
