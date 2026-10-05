"""Load the frozen market-data snapshot and flag bars whose PRICE can't be trusted.

Yahoo `=F` series are front-month continuous and NOT back-adjusted, and the mini and micro roll on
different days. Around quarterly expiries a bar can quote the old contract in one series and the new one
in the other (~1% apart for NQ). Two independent flags catch that:
  1. calendar: roll window around each quarterly expiry (3rd Friday of Mar/Jun/Sep/Dec)
  2. cross-check: the mini/micro pair (NQ/MNQ, ES/MES) disagree by more than a few ticks on a bar
Any study window that touches a flagged bar is excluded, and the exclusions are counted.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

SNAPSHOT = Path("data/market/yahoo")
PAIRS = {"NQ": "MNQ", "MNQ": "NQ", "ES": "MES", "MES": "ES"}
PAIR_TOL = {"NQ": 4.0, "MNQ": 4.0, "ES": 1.0, "MES": 1.0}  # points; normal mini/micro diff is 0-1 tick
TICK = {"NQ": 0.25, "MNQ": 0.25, "ES": 0.25, "MES": 0.25}
TF_SECONDS = {"1m": 60, "5m": 300, "1h": 3600}
ROLL_BEFORE, ROLL_AFTER = timedelta(days=9), timedelta(days=2)


def load(sym: str, tf: str, root: Path = SNAPSHOT) -> pd.DataFrame:
    path = root / f"{sym}_{tf}.csv.gz"
    df = pd.read_csv(path)
    df.index = pd.to_datetime(df.pop("ts"), unit="s", utc=True)
    return df[["open", "high", "low", "close", "volume"]].astype(float).sort_index()


def quarterly_expiries(start: date, end: date) -> list[date]:
    out = []
    for y in range(start.year - 1, end.year + 2):
        for m in (3, 6, 9, 12):
            d = date(y, m, 15)
            d += timedelta(days=(4 - d.weekday()) % 7)  # third Friday = first Friday on/after the 15th
            out.append(d)
    return out


def roll_window_mask(idx: pd.DatetimeIndex) -> np.ndarray:
    if not len(idx):
        return np.zeros(0, bool)
    d = idx.tz_convert("America/New_York").tz_localize(None).normalize()
    mask = np.zeros(len(idx), bool)
    for x in quarterly_expiries(d.min().date(), d.max().date()):
        lo, hi = pd.Timestamp(x - ROLL_BEFORE), pd.Timestamp(x + ROLL_AFTER)
        mask |= np.asarray((d >= lo) & (d <= hi))
    return mask


def pair_mismatch_mask(df: pd.DataFrame, pair: pd.DataFrame, tol: float) -> np.ndarray:
    j = pair["close"].reindex(df.index)
    diff = (df["close"] - j).abs()
    return np.asarray(diff > tol)  # NaN (pair bar missing) -> False: absence isn't evidence of a bad print


@lru_cache(maxsize=None)
def load_with_quality(sym: str, tf: str, root: str = str(SNAPSHOT)) -> pd.DataFrame:
    """Bars plus `price_bad` (roll window or pair mismatch) and `volume_bad` (zero volume) flags."""
    df = load(sym, tf, Path(root)).copy()
    bad = roll_window_mask(df.index)
    pair = PAIRS.get(sym)
    if pair and (Path(root) / f"{pair}_{tf}.csv.gz").exists():
        bad |= pair_mismatch_mask(df, load(pair, tf, Path(root)), PAIR_TOL[sym])
    df["price_bad"] = bad
    df["volume_bad"] = df["volume"] <= 0
    return df
