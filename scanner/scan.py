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

from ofcore import SYMBOLS, auction_read, gamma_levels, get_bars, trading_day
from ofcore.setups import Signal, Thresholds, detect

HERE = Path(__file__).parent
ICON = {"long": "🟢", "short": "🔴", "info": "🔵"}


def load_config(path: Path) -> dict:
    cfg = {"symbols": ["ES", "NQ", "CL", "GC", "6E"], "tf": "1h", "days": 60, "gamma": True,
           "state_file": str(HERE / ".state.json"), "thresholds": {}}
    if path.exists():
        cfg.update(tomllib.loads(path.read_text()))
    return cfg


def scan(cfg: dict) -> tuple[list[tuple[str, Signal]], list[dict]]:
    th = Thresholds(**cfg.get("thresholds", {}))
    hits, rows = [], []
    for key in cfg["symbols"]:
        if key not in SYMBOLS:
            print(f"skip unknown symbol {key}", file=sys.stderr)
            continue
        try:
            df = get_bars(key, cfg["tf"], cfg["days"])
            a = auction_read(df, SYMBOLS[key].tick)
            g = None
            if cfg.get("gamma") and SYMBOLS[key].gamma_proxy:
                try:
                    g = gamma_levels(key, a["last"])
                except Exception as e:  # options data is flaky; never kill the scan over it
                    print(f"{key}: gamma unavailable ({e})", file=sys.stderr)
            day = str(trading_day(df).iloc[-1].date())
            sigs = detect(key, df, a, g, th)
            hits += [(s.key(day), s) for s in sigs]
            rows.append({"key": key, "last": a["last"], "bias": a["bias"], "state": a["state"], "read": a["read"],
                         "rvol": a["rvol"], "signals": len(sigs), "pine": g["pine"] if g else None,
                         "regime": g["regime"] if g else None})
        except Exception as e:
            print(f"{key}: {e}", file=sys.stderr)
            rows.append({"key": key, "error": str(e)})
    return hits, rows


def print_table(rows: list[dict], hits: list[tuple[str, Signal]]) -> None:
    print(f"\n{'SYM':<7}{'LAST':>12}  {'BIAS':<8}{'STATE':<16}{'READ':<24}{'RVOL':>6}  GAMMA")
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
        print("\nGamma levels → paste into pine/of_gamma_levels.pine:")
        for k, p in pine:
            print(f"  {k:<6} {p}")


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
    # keep the file small: drop keys older than ~2 weeks
    keep = sorted(seen, key=lambda k: k.rsplit(":", 1)[-1])[-2000:]
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
