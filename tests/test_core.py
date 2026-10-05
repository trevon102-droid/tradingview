import numpy as np
import pandas as pd
import pytest

from ofcore import anchored_vwap, auction_read, build_profile, cvd, est_delta, get_bars, naked_pocs, rvol
from ofcore.auction import value_relationship
from ofcore.gamma import OptRow, levels_from_chain, zero_gamma
from ofcore.profile import Profile, auto_bin_size


def bars(rows):
    idx = pd.date_range("2026-01-05 14:00", periods=len(rows), freq="h", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx, dtype=float)


def test_profile_poc_and_value_area():
    # heavy volume at 100-101, light tails -> POC ~100.5, VA hugs it
    df = bars([[100, 101, 100, 101, 1000]] * 8 + [[104, 105, 104, 105, 50], [95, 96, 95, 96, 50]])
    p = build_profile(df, 1.0)
    assert p.poc == pytest.approx(100.5)
    assert p.val <= 100 and p.vah >= 101
    assert p.vah <= 103 and p.val >= 97
    assert abs(p.volume.sum() - df["volume"].sum()) < 1e-6


def test_value_relationship():
    mk = lambda val, vah, poc: Profile(1, np.array([]), np.array([]), poc, vah, val, vah, val)  # noqa: E731
    prev = mk(100, 110, 105)
    assert value_relationship(mk(111, 120, 115), prev) == "higher"
    assert value_relationship(mk(90, 99, 95), prev) == "lower"
    assert value_relationship(mk(102, 108, 105), prev) == "inside"
    assert value_relationship(mk(95, 115, 105), prev) == "outside"
    assert value_relationship(mk(105, 115, 110), prev) == "overlapping-higher"


def test_est_delta_sign():
    df = bars([[100, 102, 100, 102, 10], [102, 102, 100, 100, 10], [100, 101, 99, 100, 10]])
    d = est_delta(df).tolist()
    assert d == [10, -10, 0]
    assert cvd(df, reset=None).iloc[-1] == 0


def test_vwap_resets_weekly():
    df = get_bars("ES", "1h", 30, provider="demo")
    w = anchored_vwap(df, "W")
    assert w["vwap"].notna().all()
    assert (w["u2"] >= w["u1"]).all() and (w["l1"] >= w["l2"]).all()
    # first bar of each week: vwap == that bar's typical price
    tp = (df["high"] + df["low"] + df["close"]) / 3
    wk = (df.index.tz_convert("America/New_York") + pd.Timedelta(hours=7)).tz_localize(None).to_period("W-SUN")
    first = ~pd.Series(wk).duplicated().to_numpy()
    assert np.allclose(w["vwap"][first], tp[first])


def test_rvol_and_naked_pocs():
    df = get_bars("NQ", "1h", 60, provider="demo")
    r = rvol(df).dropna()
    assert len(r) > 100 and 0.5 < r.median() < 2
    from ofcore.profile import session_profiles
    sess = session_profiles(df, auto_bin_size(df, 0.25, rows=60))
    for n in naked_pocs(df, sess):
        later = df[df.index > pd.Timestamp(n["session"], unit="s", tz="UTC") + pd.Timedelta(days=1)]
        assert not ((later["low"] <= n["price"]) & (later["high"] >= n["price"])).any()


@pytest.mark.parametrize("key,tf", [("ES", "1h"), ("6E", "4h"), ("GC", "1d"), ("EURUSD", "1h")])
def test_auction_read_shape(key, tf):
    from ofcore import SYMBOLS
    df = get_bars(key, tf, 120, provider="demo")
    a = auction_read(df, SYMBOLS[key].tick)
    assert a["bias"] in {"long", "short", "neutral"}
    assert a["state"] in {"balance", "imbalance-up", "imbalance-down"}
    c = a["composite"]
    assert c["val"] <= c["poc"] <= c["vah"]
    prices = [lv["price"] for lv in a["levels"]]
    assert prices == sorted(prices, reverse=True)


def test_auto_bin_is_tick_multiple():
    df = get_bars("ES", "1h", 60, provider="demo")
    b = auto_bin_size(df, 0.25)
    assert b >= 0.25 and abs(b / 0.25 - round(b / 0.25)) < 1e-9


def test_gamma_flip_between_put_and_call_mass():
    # puts below 100, calls above -> net gamma negative low, positive high -> flip near 100
    rows = [OptRow(k, False, 1000, 0.2, 30 / 365) for k in (90, 95)] + \
           [OptRow(k, True, 1000, 0.2, 30 / 365) for k in (105, 110)]
    zg = zero_gamma(rows, 100)
    assert 96 < zg < 104
    lv = levels_from_chain(rows, 100)
    assert lv["call_wall"] in (105, 110) and lv["put_wall"] in (90, 95)


def test_zero_volume_fx_degrades_gracefully():
    from ofcore import SYMBOLS
    df = get_bars("EURUSD", "1h", 60, provider="demo").assign(volume=0.0)
    a = auction_read(df, SYMBOLS["EURUSD"].tick)
    assert a["composite"]["val"] <= a["composite"]["poc"] <= a["composite"]["vah"]
    assert a["rvol"] is None
    assert anchored_vwap(df, "W")["vwap"].notna().all()


def test_4h_buckets_stay_session_aligned_across_dst():
    """Regression: 4h bars must start 18/22/02/06/10/14 ET in winter AND summer, never straddle 18:00."""
    from ofcore.data import resample

    h = get_bars("ES", "1h", 700, provider="demo")
    four = resample(h, "4h")
    et = four.index.tz_convert("America/New_York")
    assert set(et.hour) <= {18, 22, 2, 6, 10, 14, 3}  # 03:00 only from the shifted spring-forward label
    assert (et.hour == 3).sum() <= 2
    # each 4h bar's OHLCV equals the 1h bars that fall inside its wall-clock bucket
    het = h.index.tz_convert("America/New_York")
    for t in list(et[:50]) + list(et[-50:]):
        end = t + pd.Timedelta(hours=4)
        sub = h[(het >= t) & (het < end)]
        if t.hour == 3 or sub.empty:
            continue
        row = four.loc[t.tz_convert("UTC")]
        assert row["high"] == sub["high"].max() and row["low"] == sub["low"].min()
        assert row["volume"] == sub["volume"].sum()
        assert not ((sub.index.tz_convert("America/New_York").hour == 18) & (t.hour != 18)).any()
    assert four["volume"].sum() == h["volume"].sum()  # nothing dropped or double counted
