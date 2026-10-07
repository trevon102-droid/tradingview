"""Static contract checks on the Pine sources.

These do NOT compile Pine (no TradingView compiler here). They pin down the promises the scripts make:
estimated data is labeled as estimated, alerts only fire on confirmed bars, gamma wording is neutral, and
the RTH session is 09:30-16:00 America/New_York.
"""
import re
from pathlib import Path

PINE = Path(__file__).resolve().parent.parent / "pine"


def src(name: str) -> str:
    return (PINE / name).read_text()


def alerts(text: str) -> list[str]:
    return re.findall(r"^alertcondition\((.+)$", text, re.M)


def test_no_paste_hostile_header():
    for f in PINE.glob("*.pine"):
        assert "®" not in f.read_text() and "Mozilla" not in f.read_text(), f.name


def test_delta_script_says_estimated_and_shows_source():
    s = src("of_delta_cvd.pine")
    assert 'indicator("OF · Est. Delta / Est. CVD"' in s
    for label in ('"EST. CVD"', '"EST. DELTA"', '"fallback estimate"', '"estimated intrabar ('):
        assert label in s, label
    assert "NOT bid/ask delta" in s
    assert "Closer to real footprint" not in s


def test_delta_alerts_are_confirmed_bar_gated_by_default():
    s = src("of_delta_cvd.pine")
    assert re.search(r'confOnly\s*=\s*input\.bool\(true, "Confirmed signals only"', s)
    assert "ok = not confOnly or barstate.isconfirmed" in s
    al = alerts(s)
    assert al and all(" and ok," in a for a in al), al


def test_divergence_markers_default_to_confirmation_bar():
    s = src("of_delta_cvd.pine")
    assert re.search(r'atPivot\s*=\s*input\.bool\(false', s)
    unshifted = [l for l in s.splitlines() if l.startswith("plotshape(") and "Divergence" not in l and "div ✓" in l]
    assert unshifted and all("offset" not in l for l in unshifted)
    shifted = [l for l in s.splitlines() if l.startswith("plotshape(") and "offset = -pivLen" in l]
    assert shifted and all("atPivot" in l and "known later" in l for l in shifted)


def test_rth_vwap_session_and_freeze():
    s = src("of_vwap_ema_rvol.pine")
    assert 'input.session("0930-1600"' in s and 'input.string("America/New_York"' in s
    assert "f_rthvwap(rthStart, inRth, hlc3, vol)" in s       # reset at session start, add only in session
    assert '"RTH VWAP"' in s and '"Weekly " + vw' in s and '"Monthly " + vw' in s
    assert all("barstate.isconfirmed" in a for a in alerts(s))


def test_profile_is_labeled_estimated_and_poor_extremes_are_possible():
    s = src("of_auction_profile.pine")
    assert "Est. volume profile" in s and "ESTIMATED profile" in s
    assert '"possible poor high"' in s and '"possible poor low"' in s
    assert '"poor high"' not in s.replace('"possible poor high"', "")
    assert "if not na(ibHl)" in s and "if not na(ibLl)" in s


def test_gamma_wording_is_neutral_and_levels_not_painted_on_history():
    s = src("of_gamma_levels.pine")
    low = s.lower()
    for bad in ("mean-revert", "mean revert", "trend / expansion", "pin\""):
        assert bad not in low, bad
    assert "gamma regime (est.)" in s and "STALE" in s
    assert "live   = na(calcMs) ? barstate.islast : time >= calcMs" in s
    assert "bgcolor(shade and live" in s
    al = alerts(s)
    names = " ".join(al)
    for kind in ("approach", "touch", "reject", "break", "acceptance"):
        assert f"Call wall {kind}" in names and f"Put wall {kind}" in names, kind
    for name in ("cApproach", "cTouch", "cReject", "cBreak", "cAccept", "pApproach", "pTouch", "pReject",
                 "pBreak", "pAccept", "zCross"):
        assert re.search(rf"^{name}\s*=\s*ok and", s, re.M), name   # every wall event requires a confirmed live bar


def test_qqq_strike_map_uses_held_live_ratio_and_confirmed_alerts():
    s = src("of_qqq_strike_map.pine")
    assert "gaps = barmerge.gaps_on" in s and "lookahead = barmerge.lookahead_off" in s  # stale QQQ never moves levels
    assert "liveRat := close / qqqNew" in s
    assert "not computed here" in s and "Levels as of" in s
    for name in ("callTouch", "callCross", "putTouch", "putCross", "keyHit"):
        assert re.search(rf"^{name}\s*=\s*ok and", s, re.M), name
    assert "if kStrike.size() > 0\n" in s   # Pine's 0 to -1 loop would run backwards on an empty list


def test_strike_map_touch_compares_against_prior_bar_wall():
    s = src("of_qqq_strike_map.pine")
    assert "high[1] < cwF[1]" in s and "low[1] > pwF[1]" in s
    assert "high[1] < cwF\n" not in s and "low[1] > pwF\n" not in s


def test_stale_gamma_disables_alerts():
    s = src("of_gamma_levels.pine")
    assert "staleAtBar = na(calcMs) or (time_close - calcMs) / 60000.0 > staleMin" in s
    assert re.search(r"^ok\s*=\s*live and barstate\.isconfirmed and not staleAtBar", s, re.M)


def test_cvd_divergence_never_pairs_pivots_across_a_reset():
    s = src("of_delta_cvd.pine")
    assert "epoch += resetNow ? 1 : 0" in s and "pivEpoch = epoch[pivLen]" in s
    assert "lastPhEp == pivEpoch" in s and "lastPlEp == pivEpoch" in s


def test_delta_intrabar_tf_must_be_below_chart_tf():
    s = src("of_delta_cvd.pine")
    assert "ltfBad = ltfIn != \"\" and timeframe.in_seconds(ltfIn) >= timeframe.in_seconds()" in s
    assert "not ltfBad ? ltfIn : autoLtf" in s


def test_profile_uses_explicit_cme_session_on_futures():
    s = src("of_auction_profile.pine")
    assert '"CME 18:00-17:00 ET"' in s and 'syminfo.type == "futures"' in s
    assert "cmeT   = time + 6 * 3600 * 1000" in s and '"America/New_York")' in s
    assert "newSess = useCme ? cmeDay != cmeDay[1] : timeframe.change(sessTf)" in s
    assert "sH.size() <= maxSessBar" in s        # resource guard


def test_vwap_no_volume_is_called_twap_and_rvol_na():
    s = src("of_vwap_ema_rvol.pine")
    assert "noVol = ta.cum(nz(volume)) == 0" in s and '"TWAP"' in s
    assert "rvol = noVol ? na" in s and "no volume on this feed" in s
    assert "Works on FX feeds with no volume (falls back to TWAP)" not in s
    assert "timeframe.in_seconds() <= 3600" in s
