"""Auction / orderflow scanner. Scans your list, alerts only on *new* setups.

    python -m scanner.scan                 # one pass, print + send alerts
    python -m scanner.scan --loop 60       # every 60 min
    python -m scanner.scan --dry-run       # print only, don't send or remember
    python -m scanner.scan --symbols ES,NQ,6E --tf 4h

Alerts go to whatever is configured: DISCORD_WEBHOOK_URL, and/or TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID.
Settings live in scanner/config.toml.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tomllib
from pathlib import Path

import requests

import pandas as pd

from ofcore import SYMBOLS, gamma_levels, get_bars
from ofcore.gamma import freshness
from ofcore.data import TF_MINUTES
from ofcore.setups import Signal, Thresholds, closed_bars, events

HERE = Path(__file__).parent
ICON = {"long": "🟢", "short": "🔴", "info": "🔵"}


def load_config(path: Path) -> dict:
    cfg = {"symbols": ["ES", "NQ", "CL", "GC", "6E"], "tf": "1h", "days": 60, "gamma": True, "lookback_bars": 3,
           "state_file": str(HERE / ".state.json"), "thresholds": {}}
    if path.exists():
        cfg.update(tomllib.loads(path.read_text()))
    return cfg


SYMBOL_TIMEOUT_S = 90  # one stuck Yahoo request must not hang the whole scan


def _scan_symbol(key: str, cfg: dict, th: Thresholds) -> tuple[list, dict]:
    df = closed_bars(get_bars(key, cfg["tf"], cfg["days"]), pd.Timedelta(minutes=TF_MINUTES[cfg["tf"]]))
    g = None
    if cfg.get("gamma") and SYMBOLS[key].gamma_proxy:
        try:
            g = gamma_levels(key, float(df["close"].iloc[-1]))
        except Exception as e:  # options data is flaky; never kill the scan over it
            print(f"{key}: gamma unavailable ({e})", file=sys.stderr)
    evs, a = events(key, df, SYMBOLS[key].tick, g, th, cfg.get("lookback_bars", 3))
    sigs = [s for _, s in evs]
    if cfg.get("log_events") and os.environ.get("OF_DATA", "yahoo") != "demo":
        log_live_events(key, cfg["tf"], df, a, sigs, g, SYMBOLS[key].tick)
    row = {"key": key, "last": a["last"], "bias": a["bias"], "state": a["state"], "read": a["read"],
           "rvol": a["rvol"], "signals": len(sigs), "pine": g["pine"] if g else None,
           "gamma_meta": (f"{g['proxy']}, calc {freshness(g)['calculated_et']}" if g else None),
           "regime": g["regime"] if g else None}
    return evs, row


def _with_timeout(fn, timeout: float, *args):
    """Run fn in a daemon thread; give up after `timeout` s (a hung network call can't be interrupted,
    but a daemon thread won't keep the process alive)."""
    import threading

    box: dict = {}

    def run():
        try:
            box["ok"] = fn(*args)
        except Exception as e:
            box["err"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"timed out after {timeout:.0f}s")
    if "err" in box:
        raise box["err"]
    return box["ok"]


def scan(cfg: dict) -> tuple[list[tuple[str, Signal]], list[dict]]:
    th = Thresholds(**cfg.get("thresholds", {}))
    hits, rows = [], []
    for key in cfg["symbols"]:
        if key not in SYMBOLS:
            print(f"skip unknown symbol {key}", file=sys.stderr)
            continue
        t0 = time.time()
        try:
            evs, row = _with_timeout(_scan_symbol, cfg.get("symbol_timeout_s", SYMBOL_TIMEOUT_S), key, cfg, th)
            hits += evs
            rows.append(row)
        except Exception as e:
            print(f"{key}: {e}", file=sys.stderr)
            rows.append({"key": key, "error": str(e)})
        print(f"  {key}: {time.time() - t0:.1f}s", file=sys.stderr, flush=True)
    return hits, rows


def log_live_events(sym: str, tf: str, df, a: dict, sigs: list, gamma: dict | None, tick: float) -> None:
    """Persist each event as a point-in-time research record (data/research/events/live/<date>.jsonl)."""
    from ofcore import auction_read
    from research.marketdata import roll_window_mask
    from research.records import EVENTS_DIR, append_jsonl, detector_version
    from research.replay import BAR_SECONDS, build_record, causal_context

    if not sigs or tf not in BAR_SECONDS:
        return
    bar_s = BAR_SECONDS[tf]
    ohlcv = df[["open", "high", "low", "close", "volume"]]
    ctx = causal_context(ohlcv, bar_s)
    pos = {int(t.timestamp()): i for i, t in enumerate(df.index)}
    price_bad = roll_window_mask(df.index)
    vol_bad = (df["volume"] <= 0).to_numpy()
    det = detector_version()
    recs = []
    for s in sigs:
        i = pos.get(s.bar_time, len(df) - 1)
        last = i == len(df) - 1
        # an event from a lookback bar gets the auction read of data ending at ITS bar, and no gamma
        # (the chain was fetched now, after that bar closed)
        a_i = a if last else auction_read(ohlcv.iloc[:i + 1], tick)
        recs.append(build_record(sym, tf, s, i, df, ctx, a_i, price_bad, vol_bad, "live:scanner", det, bar_s,
                                 gamma if last else None))
    day = df.index[-1].tz_convert("UTC").date().isoformat()
    append_jsonl(recs, EVENTS_DIR / "live" / f"{day}.jsonl")


def print_table(rows: list[dict], hits: list[tuple[str, Signal]]) -> None:
    print(f"\n{'SYM':<7}{'LAST':>12}  {'BIAS':<8}{'STATE':<16}{'READ':<24}{'RVOL':>6}  EST.GAMMA")
    for r in rows:
        if "error" in r:
            print(f"{r['key']:<7}{'error':>12}  {r['error'][:60]}")
            continue
        rv = f"{r['rvol']:.1f}" if r["rvol"] else "-"
        print(f"{r['key']:<7}{r['last']:>12.6g}  {r['bias']:<8}{r['state']:<16}{r['read']:<24}{rv:>6}  {r['regime'] or '-'}")
    if hits:
        print()
        for _, s in hits:
            print(f"{ICON[s.direction]} {s.symbol:<6} {s.code:<20} {s.text}")
    pine = [(r["key"], r["pine"]) for r in rows if r.get("pine")]
    if pine:
        print("\nEstimated dealer gamma (ETF proxy, assumes dealers long calls/short puts)"
              " → paste into pine/of_gamma_levels.pine:")
        meta = {r["key"]: r.get("gamma_meta") for r in rows}
        for k, p in pine:
            print(f"  {k:<6} {p}   ({meta.get(k)})")


def notify(signals: list[Signal]) -> None:
    if not signals:
        return
    lines = [f"{ICON[s.direction]} **{s.symbol}** `{s.code}` @ {s.price:g}\n{s.text}" for s in signals]
    body = "\n\n".join(lines)
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    if hook:
        for chunk in _chunks(body, 1900):
            requests.post(hook, json={"content": chunk, "username": "OF Scanner"}, timeout=10).raise_for_status()
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if tok and chat:
        for chunk in _chunks(body.replace("**", "*").replace("`", ""), 3900):
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": chunk, "parse_mode": "Markdown"}, timeout=10).raise_for_status()
    if not hook and not (tok and chat):
        print("(no DISCORD_WEBHOOK_URL / TELEGRAM_* set, so alerts were printed only)")


def _chunks(s: str, n: int):
    buf = ""
    for part in s.split("\n\n"):
        if len(buf) + len(part) + 2 > n and buf:
            yield buf
            buf = ""
        buf = f"{buf}\n\n{part}" if buf else part
    if buf:
        yield buf


def run_once(cfg: dict, dry: bool) -> None:
    cfg = {**cfg, "log_events": not dry and cfg.get("log_events", True)}
    hits, rows = scan(cfg)
    print_table(rows, hits)
    if dry:
        return
    state_path = Path(cfg["state_file"])
    seen = set(json.loads(state_path.read_text())) if state_path.exists() else set()
    fresh = [s for k, s in hits if k not in seen]
    print(f"\n{len(fresh)} new signal(s), {len(hits) - len(fresh)} already alerted")
    notify(fresh)
    seen |= {k for k, _ in hits}
    # keep the file small: newest 2000 event keys (key ends in the bar's unix time)
    keep = sorted(seen, key=lambda k: int(k.rsplit(":", 1)[-1]) if k.rsplit(":", 1)[-1].isdigit() else 0)[-2000:]
    state_path.write_text(json.dumps(keep))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Orderflow / auction scanner")
    ap.add_argument("--config", type=Path, default=HERE / "config.toml")
    ap.add_argument("--symbols", help="comma list, overrides config")
    ap.add_argument("--tf", choices=["1h", "4h", "1d"])
    ap.add_argument("--loop", type=int, metavar="MIN", help="re-scan every MIN minutes")
    ap.add_argument("--dry-run", action="store_true", help="print only; no alerts, no state")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.symbols:
        cfg["symbols"] = [s.strip().upper() for s in args.symbols.split(",")]
    if args.tf:
        cfg["tf"] = args.tf
    while True:
        run_once(cfg, args.dry_run)
        if not args.loop:
            break
        time.sleep(args.loop * 60)


if __name__ == "__main__":
    main()
