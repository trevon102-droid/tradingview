# OF Desk: orderflow / auction toolkit

My own TradingView-style setup for **swing trading futures + FX** with an orderflow / auction market lens:
volume profile, value migration, acceptance vs rejection, delta/CVD, anchored VWAPs, and dealer gamma.

Three separate tools share one engine (`ofcore/`):

| | What | Run |
|---|---|---|
| **1. Dashboard** | TV-style web app: candles, composite profile, session POC/VA, naked POCs, VWAPs, EMAs, CVD pane, auction read, gamma levels | `uvicorn dashboard.app:app --reload` → http://localhost:8000 |
| **2. Pine pack** | 4 indicators you paste into real TradingView | `pine/*.pine` |
| **3. Scanner** | Scans your list for auction setups and pings Discord/Telegram, but only on *new* signals | `python -m scanner.scan` |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                       # sanity check
```

Data comes from Yahoo by default (`ES=F`, `NQ=F`, `6E=F`, `EURUSD=X`, ...), with no API key.
Other sources:

```bash
OF_DATA=demo uvicorn dashboard.app:app     # synthetic tape, works offline
OF_DATA=csv  uvicorn dashboard.app:app     # TradingView "Export chart data" CSVs in ./data/ES_1h.csv etc.
```

Markets live in `ofcore/data.py → SYMBOLS` (ticker, tick size, options proxy). Add whatever you trade.

## 1. Dashboard

- **Watchlist** (left): every market with its auction state + read at a glance. Click to load.
- **Chart**: candles, EMA 9/21/50/200, weekly VWAP ±1/2σ, monthly VWAP, volume.
  - Right-edge **composite profile** (blue = value area, gold = POC, pink dashes = LVNs)
  - **Session boxes** = each day's value area + POC (daily chart → weekly sessions)
  - Lines: composite POC/VAH/VAL, multi-day balance VAH/VAL, **naked POCs**, **0γ / call wall / put wall**
- **CVD pane**: estimated delta + CVD (see note below)
- **Auction read** (right): bias, balance vs imbalance, value-area relationship vs prior session, acceptance or
  look-above-and-fail, CVD divergence, RVOL, next level up/down, plain-English notes
- **Gamma**: regime, flip, walls, plus a **Copy** button that gives you the string for the Pine gamma script
- Keys: `1` / `4` / `d` switch timeframe, `r` refreshes. Toggles are remembered.

## 2. Pine pack (`pine/`)

Open TradingView → Pine Editor → paste → *Add to chart*. All are Pine v6.

| File | What it does |
|---|---|
| `of_auction_profile.pine` | Composite VP on the right edge, prior-session POC + VA boxes, **naked POCs that extend until revisited**, poor high/low flags, developing POC/VA, RTH initial balance. Alert: near naked POC. |
| `of_delta_cvd.pine` | Delta + CVD from **lower-timeframe intrabars** (much closer to footprint delta than candle estimates). CVD candles / line / delta bars, weekly reset, **CVD divergences**, **absorption** markers. Alerts for all. |
| `of_vwap_ema_rvol.pine` | Weekly/monthly/quarterly anchored VWAPs with σ bands (clean breaks), EMA stack, RVOL candle highlight, readout table. Handles no-volume FX feeds. |
| `of_gamma_levels.pine` | Paste the string from the dashboard/scanner (`zg;call;put;majors`) to get 0γ flip, walls, majors, and regime shading. Alerts on flip cross / wall tags. |

## 3. Scanner

```bash
python -m scanner.scan --dry-run          # look, don't send
python -m scanner.scan                    # send new setups
python -m scanner.scan --loop 60          # every hour
python -m scanner.scan --symbols ES,NQ,6E --tf 4h
```

Set `DISCORD_WEBHOOK_URL` and/or `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`. Tune `scanner/config.toml`.
Want it running 24/5 without your machine? See `scanner/github-workflow.example.yml`.

**Setups it flags**

| Code | Meaning |
|---|---|
| `accept_above` / `accept_below` | N closes outside multi-day value. Acceptance, so go with it, old edge = support/resistance |
| `lookabove_fail` / `lookbelow_fail` | Probed outside value, got rejected back in. 80% rule, so target POC then the other edge |
| `balance_edge_high/low` | In balance, sitting on the edge, so fade until accepted |
| `naked_poc` | Within 0.5 ATR of an untested prior POC |
| `cvd_div_bullish/bearish` | New price extreme without CVD confirming |
| `vwap_pullback_long/short` | Trend (EMA 21 vs 50) pullback that held weekly VWAP |
| `rvol` | RVOL ≥ 2x |
| `gamma_flip_cross/near`, `call_wall`, `put_wall` | Dealer gamma regime change / pin-reject zones |

Each scan also prints Pine-ready gamma strings per market.

## Honest notes

- **Delta/CVD in the dashboard + scanner is estimated** from where each bar closed in its range
  (Yahoo has no bid/ask split). It's directionally solid on swing timeframes but it isn't a footprint.
  The Pine delta script uses intrabars, so trust that one more. For true footprint/bid-ask data you'd plug a
  feed like Rithmic / CQG / Databento into `ofcore/data.py`.
- **Gamma** comes from the ETF proxy's options chain (SPY→ES, QQQ→NQ, IWM→RTY, GLD→GC, USO→CL, FXE→6E...),
  scaled to the futures price. Index proxies are good. FX/commodity ETF proxies are thin, so treat them as rough context.
- Yahoo intraday is delayed and capped (~730 days of 1h). Fine for swing work, not for execution.
- Not financial advice, it's a tool. Size your risk.

## Layout

```
ofcore/      engine: data, indicators, profile, auction read, gamma, setups
dashboard/   FastAPI + static frontend (lightweight-charts vendored, Apache-2.0)
pine/        TradingView indicators
scanner/     CLI scanner + config + GH Actions template
tests/       pytest (runs on demo data, no network)
```
