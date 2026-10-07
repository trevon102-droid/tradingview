"""Event research pipeline.

    python -m research.events replay     # point-in-time replay -> data/research/events/replay/*.jsonl
    python -m research.events outcomes   # forward outcomes for events + all-bars baseline
    python -m research.events study      # scorecard.json + report.md
    python -m research.events all

Inputs: the frozen snapshot in data/market/yahoo (see research/fetch_data.py, research-data branch).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .marketdata import SNAPSHOT, TICK, load_with_quality
from .outcomes import HORIZONS_MIN, Series, outcomes_for
from .records import EVENTS_DIR, read_jsonl, write_jsonl
from .replay import BAR_SECONDS, WINDOW_DAYS, replay
from .study import (COMBOS, GAMMA, MIN_N, PRIMARY, SIGNALS, attach_baseline, baseline_table, event_frame,
                    sample_label, study_group, summarize)

SYMBOLS = ["NQ", "MNQ", "ES", "MES"]
EVENT_TFS = ["5m", "1h"]
OUTCOME_RES = ["1m", "5m", "1h"]


def _source() -> str:
    m = json.loads((SNAPSHOT / "manifest.json").read_text())
    return f"replay:yahoo-snapshot-{m['fetched_at'][:10]}"


# ---------------------------------------------------------------- replay

def _replay_chunk(args):
    sym, tf, start, end, source = args
    df = load_with_quality(sym, tf)
    return sym, tf, start, [r for r in replay(sym, tf, df, TICK[sym], source, start=start, end=end)]


def cmd_replay(symbols=SYMBOLS, tfs=EVENT_TFS, workers: int | None = None, chunk: int = 1500) -> None:
    source = _source()
    jobs = []
    for sym in symbols:
        for tf in tfs:
            n = len(load_with_quality(sym, tf))
            jobs += [(sym, tf, s, min(s + chunk, n), source) for s in range(0, n, chunk)]
    results: dict[tuple, list] = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers or os.cpu_count()) as ex:
        for k, (sym, tf, start, recs) in enumerate(ex.map(_replay_chunk, jobs), 1):
            results.setdefault((sym, tf), []).append((start, recs))
            print(f"  [{k}/{len(jobs)}] {sym} {tf} from bar {start}: {len(recs)} events  ({time.time() - t0:.0f}s)",
                  flush=True)
    for (sym, tf), parts in results.items():
        recs = [r for _, rs in sorted(parts, key=lambda x: x[0]) for r in rs]
        write_jsonl(recs, EVENTS_DIR / "replay" / f"{sym}_{tf}.jsonl.gz")
        print(f"{sym} {tf}: {len(recs)} events")


# ---------------------------------------------------------------- outcomes

def _series(sym: str) -> list[Series]:
    out = []
    for res in OUTCOME_RES:
        if (SNAPSHOT / f"{sym}_{res}.csv.gz").exists():
            out.append(Series.from_df(load_with_quality(sym, res), BAR_SECONDS[res]))
    return out


def _outcome_job(args):
    sym, kind, payload = args
    series = _series(sym)
    df = outcomes_for(payload, series)
    df["symbol"] = sym
    df["kind"] = kind
    return df


def _all_bar_pseudo_events(sym: str, tf: str) -> list[dict]:
    """Every bar as a 'long' pseudo-event: the unconditional baseline the signals must beat."""
    from .replay import causal_context

    df = load_with_quality(sym, tf)
    ctx = causal_context(df[["open", "high", "low", "close", "volume"]], BAR_SECONDS[tf])
    t = (df.index.as_unit("ns").asi8 // 10**9).astype(int)
    first = int(np.searchsorted(t, t[0] + WINDOW_DAYS[tf] * 86400))
    return [{"event_id": f"base:{sym}:{tf}:{t[i]}", "bar_open": int(t[i]), "timeframe": tf,
             "price": float(df["close"].iloc[i]), "session": ctx["session"].iloc[i],
             "context": {"atr": float(ctx["atr"].iloc[i])}} for i in range(first, len(df))]


def cmd_outcomes(symbols=SYMBOLS, tfs=EVENT_TFS, workers: int | None = None) -> None:
    jobs = []
    for sym in symbols:
        for tf in tfs:
            evs = read_jsonl(EVENTS_DIR / "replay" / f"{sym}_{tf}.jsonl.gz")
            for i in range(0, len(evs), 2000):
                jobs.append((sym, "event", evs[i:i + 2000]))
            base = _all_bar_pseudo_events(sym, tf)
            for i in range(0, len(base), 3000):
                jobs.append((sym, f"base:{tf}", base[i:i + 3000]))
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers or os.cpu_count()) as ex:
        frames = list(ex.map(_outcome_job, jobs))
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(EVENTS_DIR / "outcomes.csv.gz", index=False, compression="gzip")
    print(f"outcomes: {len(out)} rows in {time.time() - t0:.0f}s")


# ---------------------------------------------------------------- study

def _baseline_frame(out: pd.DataFrame) -> pd.DataFrame:
    base = out[out["kind"].str.startswith("base")].copy()
    base["timeframe"] = base["kind"].str.split(":").str[1]
    return base


def cmd_study() -> dict:
    out = pd.read_csv(EVENTS_DIR / "outcomes.csv.gz")
    events = []
    for p in sorted((EVENTS_DIR / "replay").glob("*.jsonl.gz")):
        events += read_jsonl(p)
    bt = baseline_table(_baseline_frame(out))
    ev_out = out[out["kind"] == "event"].drop(columns=["symbol", "kind"])
    df = attach_baseline(event_frame(events, ev_out), bt)
    df = df[df["sign"] != 0]

    excluded = (df[df["horizon"].isin(PRIMARY.values())].groupby(["event", "symbol", "timeframe"])["status"]
                .apply(lambda s: int((s != "ok").sum())).to_dict())
    rows, details = [], {}
    for sig in SIGNALS:
        for sym in SYMBOLS:
            for tf in EVENT_TFS:
                g = df[(df["event"] == sig) & (df["symbol"] == sym) & (df["timeframe"] == tf)]
                key = f"{sig}|{sym}|{tf}"
                if sig in GAMMA:
                    rows.append(_untested(sig, sym, tf, "no point-in-time options history: gamma can't be "
                                          "replayed; the live scanner logs gamma events from now on"))
                    continue
                if g.empty:
                    rows.append({**_untested(sig, sym, tf, "no events in the sample"), "status": "INSUFFICIENT_SAMPLE",
                                 "sample_size": 0})
                    continue
                res = study_group(g, tf)
                details[key] = res
                rows.append(_row(sig, sym, tf, g, res, excluded.get((sig, sym, tf), 0)))

    combos = []
    for c in COMBOS:
        if c.get("untestable"):
            combos.append({"name": c["name"], "why": c["why"], "status": "UNTESTED", "sample_size": 0})
            continue
        for sym in SYMBOLS:
            for tf in EVENT_TFS:
                g = df[(df["event"] == c["event"]) & (df["symbol"] == sym) & (df["timeframe"] == tf)]
                for k, v in c["filters"].items():
                    g = g[g[k] == v]
                if g[g["horizon"] == PRIMARY[tf]]["status"].eq("ok").sum() < MIN_N:
                    n = int(g[g["horizon"] == PRIMARY[tf]]["status"].eq("ok").sum())
                    combos.append({"name": c["name"], "symbol": sym, "timeframe": tf, "status": "INSUFFICIENT_SAMPLE",
                                   "sample_size": n, "why": c["why"]})
                    continue
                res = study_group(g, tf)
                combos.append({**_row(c["name"], sym, tf, g, res, 0), "name": c["name"], "why": c["why"]})

    n_tests = sum(1 for r in rows if r["status"] not in ("UNTESTED", "INSUFFICIENT_SAMPLE")) + \
        sum(1 for r in combos if r["status"] not in ("UNTESTED", "INSUFFICIENT_SAMPLE"))
    m = json.loads((SNAPSHOT / "manifest.json").read_text())
    card = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data": {"source": m["source"], "fetched_at": m["fetched_at"], "note": m["note"],
                 "delta": "estimated (close-location from OHLCV, not bid/ask)",
                 "gamma": "unavailable historically", "footprint": "unavailable (no tick data in snapshot)"},
        "method": {"primary_horizon_min": PRIMARY, "min_sample": MIN_N, "baseline": "all bars, same symbol/tf/session",
                   "metric": "direction-signed forward return in ATR units", "ci": "session-clustered bootstrap 95%",
                   "oos": "both chronological halves must agree",
                   "tests_run": n_tests,
                   "expected_false_positives_at_5pct": round(0.05 * n_tests, 1),
                   "note": "NQ/MNQ and ES/MES are the same markets: they are not independent confirmations",
                   "status_note": "MIXED vs WEAK: halves disagreeing by > 0.05 ATR counts as MIXED. That threshold is "
                                  "small next to 4h noise, so most MIXED rows are noise too. Both mean: no reliable "
                                  "evidence. Only PROMISING / INVALIDATED are claims, and with this many tests a few "
                                  "of those are expected by chance."},
        "signals": rows, "combinations": combos,
    }
    (EVENTS_DIR / "scorecard.json").write_text(json.dumps(card, indent=2, default=_json))
    (EVENTS_DIR / "details.json").write_text(json.dumps(details, indent=1, default=_json))
    (EVENTS_DIR / "report.md").write_text(_report(card, details))
    print(_console(card))
    return card


def _untested(sig, sym, tf, why) -> dict:
    return {"signal": sig, "symbol": sym, "timeframe": tf, "sample_size": 0, "status": "UNTESTED", "why": why,
            "data_quality": {"gamma": "unavailable"} if sig in GAMMA else {}}


def _row(sig, sym, tf, g, res, excl) -> dict:
    p = res["primary"]
    dq = {"price": "clean (degraded windows excluded)", "delta": "estimated", "gamma": "unavailable",
          "footprint": "unavailable"}
    return {
        "signal": sig, "symbol": sym, "timeframe": tf, "sample_size": p.get("n", 0),
        "sessions": p.get("n_sessions", 0), "excluded_degraded_or_missing": excl,
        "primary_horizon_min": res["primary_horizon"], "best_horizon_min_descriptive": res["best_horizon_descriptive"],
        "hit_rate": p.get("hit_rate"), "hit_ci": p.get("hit_ci"), "baseline_hit": p.get("base_hit"),
        "edge_r_atr": p.get("edge_r"), "edge_r_ci": p.get("edge_r_ci"),
        "mean_fwd_pts": p.get("mean_pts"), "median_fwd_pts": p.get("median_pts"),
        "mfe_atr": p.get("mfe_atr"), "mae_atr": p.get("mae_atr"),
        "halves_edge_r": [h.get("edge_r") for h in res["halves"]],
        "by_horizon": {h: {k: v.get(k) for k in ("n", "hit_rate", "edge_r", "mean_pts", "median_pts",
                                                   "mfe_atr", "mae_atr")} for h, v in res["by_horizon"].items()},
        "data_quality": dq,
        "statistical_confidence": f"{res['sample']} sample; "
                                  + ("edge CI excludes 0" if _ci_excl(p) else "edge CI includes 0"),
        "status": res["status"], "why": res["why"],
    }


def _ci_excl(p) -> bool:
    ci = p.get("edge_r_ci") or [math.nan, math.nan]
    return (ci[0] > 0) or (ci[1] < 0)


def _json(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, float) and math.isnan(o):
        return None
    return str(o)


def _fmt(x, f="{:+.3f}"):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f.format(x)


def _console(card) -> str:
    lines = [f"{'signal':<22}{'sym':<5}{'tf':<4}{'n':>6} {'hit':>6} {'base':>6} {'edge(ATR)':>10}  status"]
    for r in card["signals"]:
        if r["status"] == "UNTESTED" and r["symbol"] != "NQ":
            continue
        lines.append(f"{r['signal']:<22}{r['symbol']:<5}{r['timeframe']:<4}{r['sample_size']:>6} "
                     f"{_fmt(r.get('hit_rate'), '{:.2f}'):>6} {_fmt(r.get('baseline_hit'), '{:.2f}'):>6} "
                     f"{_fmt(r.get('edge_r_atr')):>10}  {r['status']}")
    return "\n".join(lines)


def _report(card, details) -> str:
    md = ["# Event study report", "",
          f"Generated {card['generated_at'][:16]}Z from {card['data']['source']} snapshot fetched "
          f"{card['data']['fetched_at'][:16]}Z. **Delta is estimated, gamma is unavailable historically, "
          "no tick-level footprint.** This is an event study, not a P&L backtest: no costs, no fills.", "",
          "## Method (fixed before results)", "",
          *[f"- **{k}**: {v}" for k, v in card["method"].items()], "",
          "## Signals (primary horizon)", "",
          "| signal | sym | tf | n | sessions | hit | baseline | edge (ATR) | edge 95% CI | halves | MFE/MAE (ATR) | status |",
          "|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|"]
    for r in card["signals"]:
        if r["status"] == "UNTESTED":
            continue
        ci = r.get("edge_r_ci") or [None, None]
        hv = r.get("halves_edge_r") or [None, None]
        md.append(f"| {r['signal']} | {r['symbol']} | {r['timeframe']} | {r['sample_size']} | {r.get('sessions', 0)} | "
                  f"{_fmt(r.get('hit_rate'), '{:.2f}')} | {_fmt(r.get('baseline_hit'), '{:.2f}')} | "
                  f"{_fmt(r.get('edge_r_atr'))} | [{_fmt(ci[0])}, {_fmt(ci[1])}] | {_fmt(hv[0])} / {_fmt(hv[1])} | "
                  f"{_fmt(r.get('mfe_atr'), '{:.2f}')} / {_fmt(r.get('mae_atr'), '{:.2f}')} | **{r['status']}** |")
    md += ["", "Untested: " + ", ".join(sorted({r["signal"] for r in card["signals"] if r["status"] == "UNTESTED"}))
           + " (no point-in-time options history).", "", "## Combinations (pre-registered)", ""]
    for c in card["combinations"]:
        md.append(f"- **{c['name']}** {c.get('symbol', '')} {c.get('timeframe', '')}: n={c['sample_size']}, "
                  f"edge={_fmt(c.get('edge_r_atr'))} ATR → **{c['status']}**")
    md += ["", "Rationale: " + "; ".join(f"_{c['name']}_: {c['why']}" for c in COMBOS)]
    md += ["", "## Horizons and segments", ""]
    for key, d in details.items():
        if d["primary"].get("n", 0) < MIN_N:
            continue
        sig, sym, tf = key.split("|")
        hz = ", ".join(f"{h}m: {_fmt(v.get('edge_r'))}" for h, v in sorted(d["by_horizon"].items()) if v.get("n", 0) >= MIN_N)
        md.append(f"- **{sig} {sym} {tf}** edge by horizon: {hz}")
        for dim, part in d["segments"].items():
            md.append(f"  - by {dim}: " + "; ".join(f"{k} n={v['n']} edge={_fmt(v['edge_r'])}" for k, v in part.items()))
    return "\n".join(md) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["replay", "outcomes", "study", "all"])
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--workers", type=int)
    a = ap.parse_args(argv)
    syms = a.symbols.split(",")
    if a.cmd in ("replay", "all"):
        cmd_replay(syms, workers=a.workers)
    if a.cmd in ("outcomes", "all"):
        cmd_outcomes(syms, workers=a.workers)
    if a.cmd in ("study", "all"):
        cmd_study()
    return 0


if __name__ == "__main__":
    sys.exit(main())
