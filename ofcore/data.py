"""Bar data. Providers: yahoo (default), csv (TradingView chart exports), demo (synthetic, offline).

Pick with env OF_DATA=yahoo|csv|demo. CSVs go in OF_CSV_DIR (default ./data) named <SYM>_<tf>.csv,
e.g. ES_1h.csv — exactly what TradingView's "Export chart data" gives you.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ET = "America/New_York"


@dataclass(frozen=True)
class Sym:
    key: str
    name: str
    yahoo: str
    tick: float
    gamma_proxy: str | None  # optionable ETF whose dealer gamma we map onto this market
    kind: str  # "future" | "fx" | "crypto"


SYMBOLS: dict[str, Sym] = {s.key: s for s in [
    # core (your red list on TradingView)
    Sym("ES", "E-mini S&P 500", "ES=F", 0.25, "SPY", "future"),
    Sym("NQ", "E-mini Nasdaq 100", "NQ=F", 0.25, "QQQ", "future"),
    Sym("MNQ", "Micro Nasdaq 100", "MNQ=F", 0.25, "QQQ", "future"),
    Sym("MES", "Micro S&P 500", "MES=F", 0.25, "SPY", "future"),
    Sym("YM", "E-mini Dow", "YM=F", 1.0, "DIA", "future"),
    Sym("CL", "Crude Oil", "CL=F", 0.01, "USO", "future"),
    # metals, rates, dollar
    Sym("GC", "Gold", "GC=F", 0.1, "GLD", "future"),
    Sym("SI", "Silver", "SI=F", 0.005, "SLV", "future"),
    Sym("DX", "US Dollar Index", "DX=F", 0.005, "UUP", "future"),
    Sym("ZN", "10Y T-Note", "ZN=F", 0.015625, None, "future"),
    Sym("ZB", "30Y T-Bond", "ZB=F", 0.03125, "TLT", "future"),
    Sym("RTY", "E-mini Russell 2000", "RTY=F", 0.1, "IWM", "future"),
    # FX
    Sym("USDJPY", "USD/JPY", "JPY=X", 0.001, None, "fx"),
    Sym("6J", "Japanese Yen", "6J=F", 0.0000005, "FXY", "future"),
    Sym("6E", "Euro FX", "6E=F", 0.00005, "FXE", "future"),
    Sym("6B", "British Pound", "6B=F", 0.0001, "FXB", "future"),
    Sym("EURUSD", "EUR/USD", "EURUSD=X", 0.00001, "FXE", "fx"),
    Sym("GBPUSD", "GBP/USD", "GBPUSD=X", 0.00001, "FXB", "fx"),
    # crypto (gamma via the spot ETFs' options)
    Sym("BTC", "Bitcoin", "BTC-USD", 0.01, "IBIT", "crypto"),
    Sym("ETH", "Ethereum", "ETH-USD", 0.01, "ETHA", "crypto"),
]}

TF_MINUTES = {"1h": 60, "4h": 240, "1d": 1440}
COLS = ["open", "high", "low", "close", "volume"]


def get_bars(key: str, tf: str = "1h", days: int = 90, provider: str | None = None) -> pd.DataFrame:
    """OHLCV indexed by UTC timestamp. tf: 1h | 4h | 1d."""
    if tf not in TF_MINUTES:
        raise ValueError(f"tf must be one of {list(TF_MINUTES)}")
    sym = SYMBOLS[key]
    provider = provider or os.environ.get("OF_DATA", "yahoo")
    base_tf = "1d" if tf == "1d" else "1h"
    if provider == "demo":
        df = _demo_bars(sym)
        if base_tf == "1d":
            df = _daily(df)
    elif provider == "csv":
        df = _csv_bars(sym, base_tf)
    else:
        df = _yahoo_bars(sym, base_tf, days)
    df = df[COLS].dropna(subset=["open", "high", "low", "close"]).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    if days:
        df = df[df.index >= df.index[-1] - pd.Timedelta(days=days)]
    return resample(df, "4h") if tf == "4h" else df


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Session-aligned N-hour bars on the ET wall clock: buckets start at the 18:00 ET CME open
    (18, 22, 02, 06, 10, 14 for 4h) all year. Binning in absolute time would slide every bucket an
    hour across DST changes and straddle the session open for half the year."""
    hours = int(pd.Timedelta(rule) / pd.Timedelta(hours=1))
    if hours < 1 or 24 % hours:
        raise ValueError("rule must divide 24h evenly, e.g. '2h', '4h', '6h'")
    wall = df.index.tz_convert(ET).tz_localize(None) + pd.Timedelta(hours=6)  # 18:00 ET -> 00:00
    start = wall.floor("D") + pd.to_timedelta((wall.hour // hours) * hours, unit="h") - pd.Timedelta(hours=6)
    out = df.groupby(start).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    # 02:00 ET doesn't exist on spring-forward day, so shift those labels forward
    out.index = out.index.tz_localize(ET, ambiguous=False, nonexistent="shift_forward").tz_convert("UTC")
    return out[~out.index.duplicated(keep="first")]


def _yahoo_bars(sym: Sym, tf: str, days: int) -> pd.DataFrame:
    import yfinance as yf  # imported lazily so demo/csv work without it

    period = f"{min(days + 5, 729)}d" if tf == "1h" else f"{max(days, 30) + 10}d"
    raw = yf.Ticker(sym.yahoo).history(period=period, interval="1h" if tf == "1h" else "1d", auto_adjust=False)
    if raw.empty:
        raise RuntimeError(f"no data from yahoo for {sym.yahoo}")
    raw = raw.rename(columns=str.lower)
    idx = raw.index
    raw.index = (idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC"))
    return raw


def _csv_bars(sym: Sym, tf: str) -> pd.DataFrame:
    path = Path(os.environ.get("OF_CSV_DIR", "data")) / f"{sym.key}_{tf}.csv"
    raw = pd.read_csv(path)
    raw.columns = [c.strip().lower() for c in raw.columns]
    t = raw["time"]
    ts = pd.to_datetime(t, unit="s", utc=True) if np.issubdtype(t.dtype, np.number) else pd.to_datetime(t, utc=True)
    raw.index = ts
    if "volume" not in raw:
        raw["volume"] = 0.0
    return raw


# --- demo data: seeded random walk with an intraday volume smile, so everything runs offline ---

_DEMO_PRICE = {"ES": 5800, "MES": 5800, "NQ": 20500, "MNQ": 20500, "YM": 42500, "RTY": 2250, "CL": 72,
               "GC": 2650, "SI": 31, "DX": 101, "ZN": 111, "ZB": 116, "6E": 1.09, "6B": 1.30, "6J": 0.0068,
               "EURUSD": 1.09, "GBPUSD": 1.30, "USDJPY": 148, "BTC": 98000, "ETH": 3400}


def _daily(df: pd.DataFrame) -> pd.DataFrame:
    """1h -> trading-day bars stamped at the trading date (17:00 ET roll)."""
    et = df.tz_convert(ET)
    key = (et.index + pd.Timedelta(hours=7)).normalize().tz_localize(None)
    out = et.groupby(key).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    out.index = out.index.tz_localize("UTC")
    return out


def _demo_bars(sym: Sym, years: float = 2.0) -> pd.DataFrame:
    """Fixed 2y hourly history per symbol so every lookback / timeframe sees the same tape."""
    rng = np.random.default_rng(sum(map(ord, sym.key)))
    end = pd.Timestamp.now(tz="UTC").floor("D")
    idx = pd.date_range(end=end, periods=int(365 * years * 24), freq="h")
    et = idx.tz_convert(ET)  # drop the daily 17:00 ET halt + weekends
    keep = (et.hour != 17) & ~((et.dayofweek == 5) | ((et.dayofweek == 4) & (et.hour >= 17)) |
                               ((et.dayofweek == 6) & (et.hour < 18)))
    idx = idx[keep]
    n = len(idx)
    p0 = _DEMO_PRICE[sym.key]
    vol = 0.0022
    # regime-switching drift gives you balance areas and trend legs to look at
    regime = np.repeat(rng.choice([-1, 0, 0, 1], size=n // 40 + 1), 40)[:n]
    rets = rng.normal(regime * vol * 0.12, vol, n)
    close = p0 * np.exp(np.cumsum(rets))
    open_ = np.r_[p0, close[:-1]]
    wick = np.abs(rng.normal(0, vol * 0.6, (2, n))) * close
    high = np.maximum(open_, close) + wick[0]
    low = np.minimum(open_, close) - wick[1]
    hour = idx.tz_convert(ET).hour
    smile = 1.0 + 2.5 * np.exp(-((hour - 10) ** 2) / 6) + 1.2 * np.exp(-((hour - 15) ** 2) / 3)
    volume = rng.gamma(4, 1, n) * smile * (1 + 40 * np.abs(rets)) * 5000
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume.round()}, index=idx)
    px = ["open", "high", "low", "close"]
    df[px] = (df[px] / sym.tick).round() * sym.tick
    return df
