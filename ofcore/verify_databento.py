"""Check the Databento CME feed against itself before trusting the footprint / DOM.

    DATABENTO_API_KEY=... python -m ofcore.verify_databento NQ --minutes 3
    DATABENTO_API_KEY=... python -m ofcore.verify_databento --all          # NQ, MNQ, ES, MES

Replays the last N minutes of BOTH `trades` and `mbp-10`, then checks:
  1. every mbp-10 TRADE print matches a `trades` record (ts, sequence, price, size, aggressor side)
  2. aggressor side is never unknown
  3. top-of-book is never crossed/locked, and bid/ask levels are sorted
  4. timestamps don't go backwards within each stream
  5. trade prints sit at/beyond the prevailing top of book (buys at the ask, sells at the bid)
  6. the continuous symbol resolved to the contract you expect to be trading
Writes data/validation/databento/latest.json and <YYYY-MM-DD>.json. Without a key it writes
status "not_run" reports: it never pretends the feed was checked.
Exit code: 0 clean, 1 failed, 2 warning, 3 not run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .feeds import FP_SYMBOLS, _side

DATASET = "GLBX.MDP3"
REPORT_DIR = Path("data/validation/databento")
DEFAULT_SYMBOLS = ["NQ", "MNQ", "ES", "MES"]
MONTH_CODE = {3: "H", 6: "M", 9: "U", 12: "Z"}
# (warn above, fail above) as fractions of the relevant record count
LIMITS = {
    "mbp_prints_missing": (0.0, 0.01), "mbp_prints_differ": (0.0, 0.001), "unknown_aggressor": (0.0, 0.01),
    "crossed_or_locked": (0.0, 0.001), "levels_unsorted": (0.0, 0.001),
    "trades_ts_backwards": (0.0, 0.001), "mbp_ts_backwards": (0.0, 0.001),
    "prints_inside_spread": (0.005, 0.05),  # a few implied/spread-leg prints are normal
}


def expected_front(d: date, root: str) -> str:
    """Calendar front month for equity-index futures (what `.c.0` tracks): rolls at the 3rd-Friday expiry."""
    for y in (d.year, d.year + 1):
        for m in (3, 6, 9, 12):
            exp = date(y, m, 15)
            exp += timedelta(days=(4 - exp.weekday()) % 7)
            if d <= exp:
                return f"{root}{MONTH_CODE[m]}{y % 10}"
    raise ValueError(d)


def collect(sym_key: str, minutes: float, key: str, max_records: int = 2_000_000) -> dict:
    """Pull both streams and count everything. Pure data gathering; judging happens in evaluate()."""
    import databento as db
    from databento_dbn import F_LAST

    sym = FP_SYMBOLS[sym_key]
    end_ns = time.time_ns()
    start = end_ns - int(minutes * 60e9)
    client = db.Live(key=key)
    for schema in ("trades", "mbp-10"):
        client.subscribe(dataset=DATASET, schema=schema, stype_in="continuous", symbols=[sym.feed_symbol], start=start)

    trades: dict[tuple[int, int], tuple] = {}
    mbp_prints: list[tuple] = []
    c = Counter()
    last_ts = {"trades": 0, "mbp": 0}
    bid = ask = None
    resolved = set()
    S = 1e9
    for n, rec in enumerate(client):
        if n >= max_records or getattr(rec, "ts_event", 0) > end_ns:
            break
        if hasattr(rec, "stype_out_symbol"):  # SymbolMappingMsg: which real contract the continuous symbol is
            resolved.add(str(rec.stype_out_symbol))
            continue
        if isinstance(rec, db.TradeMsg):
            c["trades"] += 1
            if rec.ts_event < last_ts["trades"]:
                c["trades_ts_backwards"] += 1
            last_ts["trades"] = rec.ts_event
            trades[(rec.ts_event, rec.sequence)] = (rec.price / S, rec.size, _side(rec.side))
        elif isinstance(rec, db.MBP10Msg):
            c["mbp"] += 1
            if rec.ts_event < last_ts["mbp"]:
                c["mbp_ts_backwards"] += 1
            last_ts["mbp"] = rec.ts_event
            if _side(rec.action) == "T":
                px, side = rec.price / S, _side(rec.side)
                mbp_prints.append(((rec.ts_event, rec.sequence), (px, rec.size, side)))
                if side == "N":
                    c["unknown_aggressor"] += 1
                elif bid is not None and ask is not None:
                    if (side == "B" and px < ask - 1e-9) or (side == "A" and px > bid + 1e-9):
                        c["prints_inside_spread"] += 1
            if rec.flags & F_LAST:
                bids = [x.bid_px / S for x in rec.levels if x.bid_sz > 0]
                asks = [x.ask_px / S for x in rec.levels if x.ask_sz > 0]
                if bids != sorted(bids, reverse=True) or asks != sorted(asks):
                    c["levels_unsorted"] += 1
                if bids and asks:
                    if bids[0] >= asks[0]:
                        c["crossed_or_locked"] += 1
                    bid, ask = bids[0], asks[0]
                c["books"] += 1
    client.stop()
    c["mbp_prints"] = len(mbp_prints)
    c["mbp_prints_matched"] = sum(1 for k, v in mbp_prints if trades.get(k) == v)
    c["mbp_prints_missing"] = sum(1 for k, _ in mbp_prints if k not in trades)
    c["mbp_prints_differ"] = sum(1 for k, v in mbp_prints if k in trades and trades[k] != v)
    c["_differ_examples"] = [[list(k), list(v), list(trades[k])] for k, v in mbp_prints if k in trades and trades[k] != v][:5]
    return {"counts": dict(c), "resolved": sorted(resolved), "feed_symbol": sym.feed_symbol}


def evaluate(sym_key: str, minutes: float, raw: dict, today: date | None = None) -> dict:
    c = raw["counts"]
    denom = {"mbp_prints_missing": c.get("mbp_prints", 0), "mbp_prints_differ": c.get("mbp_prints", 0),
             "unknown_aggressor": c.get("mbp_prints", 0), "prints_inside_spread": c.get("mbp_prints", 0),
             "crossed_or_locked": c.get("books", 0), "levels_unsorted": c.get("books", 0),
             "trades_ts_backwards": c.get("trades", 0), "mbp_ts_backwards": c.get("mbp", 0)}
    checks, worst, notes = {}, "clean", []
    for name, (warn, fail) in LIMITS.items():
        v, n = int(c.get(name, 0)), denom[name]
        frac = v / n if n else 0.0
        level = "failed" if frac > fail else "warning" if frac > warn else "clean"
        checks[name] = {"count": v, "of": n, "fraction": round(frac, 6), "warn_above": warn, "fail_above": fail,
                        "result": level}
        worst = _worse(worst, level)
    if not c.get("trades") or not c.get("mbp") or not c.get("mbp_prints"):
        worst = "failed"
        notes.append("no trades / mbp-10 / prints received: the feed returned nothing to verify")

    root = FP_SYMBOLS[sym_key].feed_symbol.split(".")[0]
    exp = expected_front(today or datetime.now(timezone.utc).date(), root)
    resolved = raw.get("resolved") or []
    if not resolved:
        mapping = "not_observed"
        notes.append("continuous-symbol mapping message not observed; contract could not be confirmed")
    elif exp in resolved:
        mapping = "ok"
    else:
        mapping = "mismatch"
        worst = _worse(worst, "warning")
        notes.append(f"`{raw['feed_symbol']}` resolved to {resolved}, calendar front month is {exp}. "
                     "During roll week volume moves to the next contract before expiry: decide which one you trade.")
    checks["contract_mapping"] = {"expected_calendar_front": exp, "resolved": resolved, "result": mapping}
    notes.append("`.c.0` = calendar front month (rolls at expiry). Traders usually roll ~8 days earlier on volume; "
                 "`.v.0` tracks the highest-volume contract if that matches your workflow better.")
    if c.get("_differ_examples"):
        notes.append(f"examples of differing prints (key, mbp, trades): {c['_differ_examples']}")
    return {
        "symbol": sym_key, "dataset": DATASET, "feed_symbol": raw["feed_symbol"],
        "verified_at": datetime.now(timezone.utc).isoformat(), "minutes": minutes, "status": worst,
        "checks": checks,
        "records": {k: int(c.get(k, 0)) for k in ("trades", "mbp", "books", "mbp_prints", "mbp_prints_matched",
                                                   "mbp_prints_missing", "mbp_prints_differ")},
        "notes": notes,
    }


def not_run(sym_key: str, minutes: float, reason: str) -> dict:
    return {"symbol": sym_key, "dataset": DATASET, "feed_symbol": FP_SYMBOLS[sym_key].feed_symbol,
            "verified_at": None, "attempted_at": datetime.now(timezone.utc).isoformat(), "minutes": minutes,
            "status": "not_run", "reason": reason, "checks": {}, "records": {},
            "notes": ["Real CME order flow is UNVERIFIED. Footprint/DOM output for CME futures must not be trusted."]}


def _worse(a: str, b: str) -> str:
    order = ["clean", "warning", "failed"]
    return max(a, b, key=order.index)


def write_reports(reports: list[dict], out: Path = REPORT_DIR) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).date().isoformat()
    dated = out / f"{day}.json"
    prior = json.loads(dated.read_text())["reports"] if dated.exists() else []
    merged = {r["symbol"]: r for r in prior}
    merged.update({r["symbol"]: r for r in reports})
    doc = {"generated_at": datetime.now(timezone.utc).isoformat(), "reports": list(merged.values())}
    dated.write_text(json.dumps(doc, indent=2))
    (out / "latest.json").write_text(json.dumps(doc, indent=2))
    return out / "latest.json"


def _print(r: dict) -> None:
    print(f"\n{r['symbol']} ({r['feed_symbol']}): {r['status'].upper()}")
    if r["status"] == "not_run":
        print(f"  reason: {r['reason']}")
        return
    rec = r["records"]
    print(f"  trades records      {rec['trades']:>10,}")
    print(f"  mbp-10 records      {rec['mbp']:>10,}   books published (F_LAST): {rec['books']:,}")
    print(f"  mbp-10 prints       {rec['mbp_prints']:>10,}   matched to trades: {rec['mbp_prints_matched']:,}")
    label = {"mbp_prints_missing": "mbp prints missing from trades", "mbp_prints_differ": "mbp prints that differ from trades",
             "unknown_aggressor": "unknown aggressor side", "crossed_or_locked": "crossed/locked top of book",
             "levels_unsorted": "unsorted levels", "trades_ts_backwards": "trades ts going backwards",
             "mbp_ts_backwards": "mbp ts going backwards", "prints_inside_spread": "prints inside the prior spread"}
    for k, v in r["checks"].items():
        if k == "contract_mapping":
            print(f"  {'OK ' if v['result'] == 'ok' else '!! '} contract: expected {v['expected_calendar_front']}, "
                  f"resolved {v['resolved'] or 'not observed'}")
            continue
        mark = {"clean": "OK ", "warning": "?? ", "failed": "!! "}[v["result"]]
        print(f"  {mark} {label[k]:<36}{v['count']:>8,}")
    for n in r["notes"]:
        print(f"  - {n}")
    print("\nCLEAN" if r["status"] == "clean" else f"\n{r['status'].upper()}: check the items marked above")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", choices=[k for k, s in FP_SYMBOLS.items() if s.feed == "databento"])
    ap.add_argument("--all", action="store_true", help="NQ, MNQ, ES, MES")
    ap.add_argument("--minutes", type=float, default=3)
    ap.add_argument("--max-records", type=int, default=2_000_000)
    ap.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    args = ap.parse_args(argv)
    syms = DEFAULT_SYMBOLS if args.all or not args.symbol else [args.symbol]
    key = os.environ.get("DATABENTO_API_KEY")
    reports = []
    for s in syms:
        if not key:
            reports.append(not_run(s, args.minutes, "DATABENTO_API_KEY unavailable"))
            continue
        try:
            reports.append(evaluate(s, args.minutes, collect(s, args.minutes, key, args.max_records)))
        except Exception as e:  # network/auth/subscription errors are a failed verification, not a crash
            r = not_run(s, args.minutes, f"error: {e}")
            r["status"] = "failed"
            reports.append(r)
    for r in reports:
        _print(r)
    path = write_reports(reports, args.report_dir)
    print(f"\nreport: {path}")
    worst = [r["status"] for r in reports]
    return 1 if "failed" in worst else 2 if "warning" in worst else 3 if "not_run" in worst else 0


if __name__ == "__main__":
    sys.exit(main())
