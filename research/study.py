"""Event study + scorecard. Every rule here was fixed before looking at results.

Directional metric: r = sign * forward_points / ATR(event bar), so NQ and ES are comparable and a
short that works is positive. Baseline: the same long/short metric over ALL bars of the same symbol,
timeframe and session (RTH/ETH), so a long signal in a rising market doesn't get credit for the drift.
Edge = event metric - baseline metric.

Status uses ONE pre-registered horizon per timeframe (PRIMARY). `best_horizon` is descriptive only.
  INSUFFICIENT_SAMPLE  n < 30 at the primary horizon
  PROMISING            edge > 0 with 95% session-clustered bootstrap CI above 0, hit rate's Wilson
                       lower bound above baseline, AND positive edge in both chronological halves
  INVALIDATED          n >= 100 and the edge is significantly NEGATIVE (CI below 0, Wilson upper bound
                       below baseline) in a consistent way across halves: the signal points the wrong way
  MIXED                the two halves disagree in sign by a material amount (> 0.05 ATR)
  WEAK                 otherwise: not distinguishable from the baseline
Sample labels: <30 insufficient, 30-99 preliminary, 100+ stronger. These are research labels, not proof.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ofcore.sessions import cme_session_of

PRIMARY = {"5m": 30, "1h": 240}
MIN_N = 30
STRONG_N = 100
MIN_SEGMENT_N = 30
MATERIAL = 0.05  # ATR
SIGNALS = ["accept_above", "accept_below", "lookabove_fail", "lookbelow_fail", "balance_edge_high",
           "balance_edge_low", "naked_poc", "cvd_div_bullish", "cvd_div_bearish", "vwap_pullback_long",
           "vwap_pullback_short", "rvol", "gamma_flip_cross", "gamma_flip_near", "call_wall", "put_wall"]
GAMMA = {"gamma_flip_cross", "gamma_flip_near", "call_wall", "put_wall"}

# Pre-registered combinations: a handful of economically motivated hypotheses, no search.
COMBOS = [
    {"name": "cvd_div_bearish + below RTH VWAP + bear EMA stack", "event": "cvd_div_bearish",
     "filters": {"vs_rth_vwap": "below", "ema_stack": "bear"},
     "why": "fading aggression at a high while the session's value (RTH VWAP) and trend already point down"},
    {"name": "cvd_div_bullish + above RTH VWAP + bull EMA stack", "event": "cvd_div_bullish",
     "filters": {"vs_rth_vwap": "above", "ema_stack": "bull"}, "why": "mirror of the above"},
    {"name": "lookabove_fail + high RVOL + below weekly VWAP", "event": "lookabove_fail",
     "filters": {"rvol_bucket": "high", "vs_weekly_vwap": "below"},
     "why": "a failed breakout on heavy participation against the weekly value area"},
    {"name": "lookbelow_fail + high RVOL + above weekly VWAP", "event": "lookbelow_fail",
     "filters": {"rvol_bucket": "high", "vs_weekly_vwap": "above"}, "why": "mirror of the above"},
    {"name": "gamma flip + RTH VWAP rejection + high RVOL", "event": "gamma_flip_cross", "filters": {},
     "why": "needs point-in-time gamma history, which doesn't exist yet", "untestable": True},
]
SEGMENTS = ["session", "regime", "vs_rth_vwap", "rvol_bucket", "gamma_regime"]


# ---------------------------------------------------------------- statistics

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def cluster_boot(values: np.ndarray, clusters: np.ndarray, reps: int = 1000, seed: int = 7) -> tuple[float, float]:
    """95% CI of the mean, resampling whole sessions (events on the same day aren't independent)."""
    if len(values) < 2:
        return (math.nan, math.nan)
    rng = np.random.default_rng(seed)
    uniq, inv = np.unique(clusters, return_inverse=True)
    sums = np.bincount(inv, weights=values)
    cnts = np.bincount(inv).astype(float)
    k = len(uniq)
    draws = rng.integers(0, k, size=(reps, k))
    means = sums[draws].sum(1) / cnts[draws].sum(1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def sample_label(n: int) -> str:
    return "insufficient" if n < MIN_N else "preliminary" if n < STRONG_N else "stronger"


# ---------------------------------------------------------------- frames

def event_frame(events: list[dict], outcomes: pd.DataFrame) -> pd.DataFrame:
    """Join events with their outcomes and apply the direction sign."""
    ev = pd.DataFrame([{
        "event_id": e["event_id"], "ts": pd.Timestamp(e["timestamp"]), "symbol": e["symbol"],
        "timeframe": e["timeframe"], "event": e["event"], "session": e["session"],
        "direction": e["direction"], "hypothesis": e["hypothesis"], "price": e["price"], "level": e["level"],
        **{k: e["context"].get(k) for k in ("regime", "vs_rth_vwap", "vs_weekly_vwap", "rvol_bucket",
                                            "ema_stack", "gamma_regime", "bar_direction")},
        "dq_price": e["data_quality"].get("price"), "dq_delta": e["data_quality"].get("delta"),
        "dq_gamma": e["data_quality"].get("gamma"), "dq_volume": e["data_quality"].get("volume"),
    } for e in events])
    if ev.empty:
        return ev
    ev["sign"] = ev.apply(_sign, axis=1)
    ev["cme_session"] = [cme_session_of(t.timestamp()) for t in ev["ts"]]
    df = ev.merge(outcomes.drop(columns=["session"], errors="ignore"), on="event_id", how="left")
    ok = df["status"] == "ok"
    s = df["sign"].astype(float)
    df["r"] = np.where(ok, s * df["fwd_pts"] / df["atr"], np.nan)
    df["fwd_signed_pts"] = np.where(ok, s * df["fwd_pts"], np.nan)
    df["mfe_atr"] = np.where(ok, np.where(s > 0, df["mfe_pts"], df["mae_pts"]) / df["atr"], np.nan)
    df["mae_atr"] = np.where(ok, np.where(s > 0, df["mae_pts"], df["mfe_pts"]) / df["atr"], np.nan)
    df["mfe_signed_pts"] = np.where(ok, np.where(s > 0, df["mfe_pts"], df["mae_pts"]), np.nan)
    df["mae_signed_pts"] = np.where(ok, np.where(s > 0, df["mae_pts"], df["mfe_pts"]), np.nan)
    df["t_fav"] = np.where(s > 0, df.get("t_up_min"), df.get("t_dn_min"))
    df["t_adv"] = np.where(s > 0, df.get("t_dn_min"), df.get("t_up_min"))
    return df


def _sign(e) -> int:
    if e["direction"] == "long":
        return 1
    if e["direction"] == "short":
        return -1
    if e["hypothesis"] == "toward_level" and e["level"] is not None:
        return int(np.sign(e["level"] - e["price"]))
    if e["hypothesis"] == "with_bar":
        return {"up": 1, "down": -1}.get(e["bar_direction"], 0)
    return 0


def baseline_table(base: pd.DataFrame) -> pd.DataFrame:
    """Long-side stats over ALL bars per (symbol, timeframe, session, horizon)."""
    b = base[base["status"] == "ok"].copy()
    b["r_long"] = b["fwd_pts"] / b["atr"]
    g = b.groupby(["symbol", "timeframe", "session", "horizon"])
    return pd.DataFrame({"p_up": g["fwd_pts"].apply(lambda x: (x > 0).mean()),
                         "p_dn": g["fwd_pts"].apply(lambda x: (x < 0).mean()),
                         "mean_r_long": g["r_long"].mean(), "n_bars": g.size()}).reset_index()


def attach_baseline(df: pd.DataFrame, bt: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(bt, on=["symbol", "timeframe", "session", "horizon"], how="left")
    df["base_hit"] = np.where(df["sign"] > 0, df["p_up"], df["p_dn"])
    df["base_r"] = df["sign"] * df["mean_r_long"]
    return df


# ---------------------------------------------------------------- summaries

def summarize(g: pd.DataFrame, boot: bool = False) -> dict:
    g = g[g["status"] == "ok"]
    n = len(g)
    if n == 0:
        return {"n": 0}
    hits = int((g["r"] > 0).sum())
    lo, hi = wilson(hits, n)
    out = {
        "n": n, "n_sessions": int(g["cme_session"].nunique()),
        "hit_rate": hits / n, "hit_ci": [lo, hi], "opp_hit_rate": float((g["r"] < 0).mean()),
        "base_hit": float(g["base_hit"].mean()), "edge_hit": hits / n - float(g["base_hit"].mean()),
        "mean_r": float(g["r"].mean()), "median_r": float(g["r"].median()),
        "base_r": float(g["base_r"].mean()), "edge_r": float((g["r"] - g["base_r"]).mean()),
        "mean_pts": float(g["fwd_signed_pts"].mean()), "median_pts": float(g["fwd_signed_pts"].median()),
        "mfe_atr": float(g["mfe_atr"].mean()), "mae_atr": float(g["mae_atr"].mean()),
        "mfe_pts": float(g["mfe_signed_pts"].mean()), "mae_pts": float(g["mae_signed_pts"].mean()),
        "max_excursion_atr": float(np.maximum(g["mfe_atr"], g["mae_atr"]).mean()),
        "t_fav_median_min": _nanmed(g["t_fav"]), "t_adv_median_min": _nanmed(g["t_adv"]),
        "res_used": sorted(int(x) for x in g["res"].dropna().unique()),
    }
    if boot:
        out["edge_r_ci"] = list(cluster_boot((g["r"] - g["base_r"]).to_numpy(), g["cme_session"].astype(str).to_numpy()))
    return out


def _nanmed(s) -> float | None:
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.median()) if len(s) else None


def halves(g: pd.DataFrame) -> tuple[dict, dict]:
    g = g[g["status"] == "ok"].sort_values("ts")
    mid = len(g) // 2
    return summarize(g.iloc[:mid]), summarize(g.iloc[mid:])


def status_for(s: dict, a: dict, b: dict) -> tuple[str, str]:
    n = s.get("n", 0)
    if n < MIN_N:
        return "INSUFFICIENT_SAMPLE", f"n={n} < {MIN_N}"
    ci = s.get("edge_r_ci", [math.nan, math.nan])
    ea, eb = a.get("edge_r", 0.0), b.get("edge_r", 0.0)
    if ci[0] > 0 and s["hit_ci"][0] > s["base_hit"] and ea > 0 and eb > 0:
        return "PROMISING", "edge CI > 0, hit-rate CI above baseline, positive in both halves"
    if n >= STRONG_N and ci[1] < 0 and s["hit_ci"][1] < s["base_hit"] and ea < 0 and eb < 0:
        return "INVALIDATED", "edge significantly negative in both halves: signal points the wrong way"
    if np.sign(ea) != np.sign(eb) and max(abs(ea), abs(eb)) > MATERIAL:
        return "MIXED", f"halves disagree (edge {ea:+.3f} vs {eb:+.3f} ATR)"
    return "WEAK", "not distinguishable from the all-bars baseline"


def study_group(g: pd.DataFrame, tf: str) -> dict:
    prim = PRIMARY[tf]
    by_h = {int(h): summarize(gh) for h, gh in g.groupby("horizon")}
    gp = g[g["horizon"] == prim]
    main = summarize(gp, boot=True)
    a, b = halves(gp)
    status, why = status_for(main, a, b)
    ranked = [(h, v["edge_r"]) for h, v in by_h.items() if v.get("n", 0) >= MIN_N]
    best = max(ranked, key=lambda x: x[1])[0] if ranked else None
    segs = {}
    for dim in SEGMENTS:
        part = {}
        for val, gs in gp.groupby(dim, dropna=True):
            sm = summarize(gs)
            if sm.get("n", 0) >= MIN_SEGMENT_N:
                part[str(val)] = {k: sm[k] for k in ("n", "hit_rate", "base_hit", "edge_hit", "edge_r", "mean_r")}
        if len(part) >= 2:  # a segmentation is only shown when at least two sides have enough sample
            segs[dim] = part
    return {"primary_horizon": prim, "primary": main, "halves": [a, b], "by_horizon": by_h,
            "best_horizon_descriptive": best, "status": status, "why": why, "segments": segs,
            "sample": sample_label(main.get("n", 0))}
