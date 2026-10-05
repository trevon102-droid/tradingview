"""Download a frozen snapshot of real CME index-futures bars for the event study.

Runs on GitHub Actions (this repo's dev container can't reach Yahoo). Output:
    data/market/yahoo/<SYM>_<tf>.csv.gz   columns: ts (unix sec, bar open, UTC), open, high, low, close, volume
    data/market/yahoo/manifest.json       fetched_at, source, per-file rows/first/last
Yahoo limits: 1m back ~30 days (max 7 days per request), 5m back 60 days, 1h back ~730 days.
Yahoo `=F` symbols are front-month continuous WITHOUT back-adjustment: expect jumps at quarterly rolls.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

SYMBOLS = {"NQ": "NQ=F", "MNQ": "MNQ=F", "ES": "ES=F", "MES": "MES=F"}
OUT = Path("data/market/yahoo")


def _norm(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.rename(columns=str.lower)
    idx = raw.index.tz_localize("UTC") if raw.index.tz is None else raw.index.tz_convert("UTC")
    df = pd.DataFrame({"ts": (idx.asi8 // 10**9).astype("int64"),
                       **{c: raw[c].to_numpy() for c in ["open", "high", "low", "close", "volume"]}})
    return df.dropna(subset=["open", "high", "low", "close"]).drop_duplicates("ts").sort_values("ts")


def fetch(ticker: str, tf: str) -> pd.DataFrame:
    import yfinance as yf

    tk = yf.Ticker(ticker)
    if tf == "1m":  # 7-day chunks, ~29 days back
        end = datetime.now(timezone.utc)
        parts = []
        for k in range(4):
            e = end - timedelta(days=7 * k)
            s = e - timedelta(days=7)
            raw = tk.history(interval="1m", start=s, end=e, auto_adjust=False, prepost=True)
            if not raw.empty:
                parts.append(_norm(raw))
            time.sleep(1)
        return pd.concat(parts).drop_duplicates("ts").sort_values("ts") if parts else pd.DataFrame()
    period = {"5m": "60d", "1h": "730d"}[tf]
    raw = tk.history(interval=tf, period=period, auto_adjust=False, prepost=True)
    return _norm(raw) if not raw.empty else pd.DataFrame()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"fetched_at": datetime.now(timezone.utc).isoformat(), "source": "yahoo finance (yfinance), delayed",
                "note": "front-month continuous, not back-adjusted", "files": {}}
    failed = 0
    for key, tic in SYMBOLS.items():
        for tf in ("1m", "5m", "1h"):
            try:
                df = fetch(tic, tf)
            except Exception as e:  # keep going; the manifest records the failure
                df, err = pd.DataFrame(), str(e)[:300]
            else:
                err = None if len(df) else "no rows"
            name = f"{key}_{tf}.csv.gz"
            if len(df):
                df.to_csv(OUT / name, index=False, compression="gzip")
            else:
                failed += 1
            manifest["files"][name] = {"ticker": tic, "rows": int(len(df)), "error": err,
                                       "first": int(df["ts"].iloc[0]) if len(df) else None,
                                       "last": int(df["ts"].iloc[-1]) if len(df) else None}
            print(f"{name:<16} rows={len(df):>7} {err or ''}")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return 0 if failed < len(SYMBOLS) * 3 else 1


if __name__ == "__main__":
    sys.exit(main())
