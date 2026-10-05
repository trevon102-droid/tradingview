"""Check the Databento CME feed against itself before trusting the footprint / DOM.

    DATABENTO_API_KEY=... python -m ofcore.verify_databento ES --minutes 3

Replays the last N minutes of BOTH `trades` and `mbp-10`, then checks:
  1. every mbp-10 TRADE print matches a `trades` record (ts, sequence, price, size, aggressor side)
  2. aggressor side is never unknown
  3. top-of-book is never crossed, and bid/ask levels are sorted
  4. timestamps don't go backwards within each stream
  5. trade prints sit at/near the prevailing top of book (buy prints at the ask, sell at the bid)
Exit code 0 = clean, 1 = something to look at.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter

from .feeds import FP_SYMBOLS, _side


def main(argv: list[str] | None = None) -> int:
    import os

    import databento as db
    from databento_dbn import F_LAST

    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", choices=[k for k, s in FP_SYMBOLS.items() if s.feed == "databento"])
    ap.add_argument("--minutes", type=float, default=3)
    ap.add_argument("--max-records", type=int, default=2_000_000)
    args = ap.parse_args(argv)
    sym = FP_SYMBOLS[args.symbol]
    key = os.environ.get("DATABENTO_API_KEY") or sys.exit("set DATABENTO_API_KEY")

    end_ns = time.time_ns()
    start = end_ns - int(args.minutes * 60e9)
    client = db.Live(key=key)
    for schema in ("trades", "mbp-10"):
        client.subscribe(dataset="GLBX.MDP3", schema=schema, stype_in="continuous",
                         symbols=[sym.feed_symbol], start=start)

    trades: dict[tuple[int, int], tuple] = {}
    mbp_prints: list[tuple] = []
    c = Counter()
    last_ts = {"trades": 0, "mbp": 0}
    bid = ask = None
    S = 1e9
    for n, rec in enumerate(client):
        if n >= args.max_records or getattr(rec, "ts_event", 0) > end_ns:
            break
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
                    c["unknown_side"] += 1
                elif bid is not None and ask is not None:
                    # buy aggressor should print at/above the prior ask, sell at/below the prior bid
                    if (side == "B" and px < ask - 1e-9) or (side == "A" and px > bid + 1e-9):
                        c["print_inside_spread"] += 1
            if rec.flags & F_LAST:
                lv = rec.levels
                bids = [x.bid_px / S for x in lv if x.bid_sz > 0]
                asks = [x.ask_px / S for x in lv if x.ask_sz > 0]
                if bids != sorted(bids, reverse=True) or asks != sorted(asks):
                    c["levels_unsorted"] += 1
                if bids and asks:
                    if bids[0] >= asks[0]:
                        c["crossed_or_locked"] += 1
                    bid, ask = bids[0], asks[0]
                c["books"] += 1
    client.stop()

    matched = sum(1 for k, v in mbp_prints if trades.get(k) == v)
    missing = [(k, v) for k, v in mbp_prints if k not in trades]
    differ = [(k, v, trades[k]) for k, v in mbp_prints if k in trades and trades[k] != v]
    print(f"\n{sym.key} ({sym.feed_symbol}), last {args.minutes:g} min")
    print(f"  trades records      {c['trades']:>10,}")
    print(f"  mbp-10 records      {c['mbp']:>10,}   books published (F_LAST): {c['books']:,}")
    print(f"  mbp-10 prints       {len(mbp_prints):>10,}   matched to trades: {matched:,}")
    problems = {
        "mbp prints missing from trades": len(missing),
        "mbp prints that differ from trades": len(differ),
        "unknown aggressor side": c["unknown_side"],
        "crossed/locked top of book": c["crossed_or_locked"],
        "unsorted levels": c["levels_unsorted"],
        "trades ts going backwards": c["trades_ts_backwards"],
        "mbp ts going backwards": c["mbp_ts_backwards"],
        "prints inside the prior spread": c["print_inside_spread"],
    }
    for k, v in problems.items():
        print(f"  {'OK ' if v == 0 else '!! '} {k:<36}{v:>8,}")
    for k, v, t in differ[:5]:
        print(f"     differ {k}: mbp={v} trades={t}")
    bad = {k: v for k, v in problems.items() if v}
    # a few prints inside the spread are normal (implied/spread legs); flag only if it's common
    if bad.get("prints inside the prior spread", 0) <= max(5, len(mbp_prints) // 200):
        bad.pop("prints inside the prior spread", None)
    print("\nCLEAN" if not bad else f"\nCHECK THESE: {', '.join(bad)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
