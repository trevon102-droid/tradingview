# OF Desk: orderflow / auction toolkit

My own TradingView-style setup for **swing trading futures + FX** with an orderflow / auction market lens:
volume profile, value migration, acceptance vs rejection, delta/CVD, anchored VWAPs, and dealer gamma.

Three separate tools share one engine (`ofcore/`):

| | What | Run |
|---|---|---|
| **1. Dashboard** | TV-style web app: candles, composite profile, session POC/VA, naked POCs, VWAPs, EMAs, CVD pane, auction read, gamma levels | `uvicorn dashboard.app:app --reload` → http://localhost:8000 |
| **1b. Footprint + DOM** | Bid×ask per price inside every candle, diagonal imbalances, stacked-imbalance zones, unfinished auctions, plus a DOM ladder + time & sales | same server → http://localhost:8000/footprint |
| **2. Pine pack** | 5 indicators you paste into real TradingView | `pine/*.pine` |
| **3. Scanner** | Scans your list for auction setups and pings Discord/Telegram, but only on *new* signals | `python -m scanner.scan` |

## What's real and what's estimated (read this first)

| Thing | What it actually is | Label in the tools |
|---|---|---|
| **True order flow** | Every trade with its aggressor side, from **Databento (CME)** or **Kraken (BTC/ETH)**. Used only by the `/footprint` page. **CME path: UNVERIFIED** until `verify_databento` passes on real data (see `data/validation/databento/latest.json`). | footprint, DOM `L2 · top 10` |
| **Estimated delta / CVD** | Guessed from candles: dashboard + scanner use where each bar closed in its range; the Pine script uses lower-timeframe candle direction. **Neither is bid/ask delta.** | `Est. delta`, `EST. CVD`, Pine `Source: estimated intrabar / fallback estimate` |
| **Estimated volume profile** | Each bar's volume spread evenly over its price range. Not true volume-at-price. | `Est. volume profile` |
| **Estimated dealer gamma** | Computed from an **ETF proxy's** option chain (SPY→ES, QQQ→NQ) assuming dealers are long calls / short puts, scaled to futures. **Not observed futures-options gamma.** Has a calculation time and goes **STALE**. | `Est. dealer gamma`, `Positive/Negative gamma regime (est.)` |
| **RTH data** | 09:30–16:00 America/New_York on NYSE trading days (13:00 on early closes), DST-safe, from `ofcore/sessions.py`. | `RTH`, `RTH VWAP` |
| **Research events** | Point-in-time records of every setup the detector fires, with the context known at that moment and a `data_quality` block (`clean / estimated / degraded / unknown / unavailable`). | `data/research/events/` |
| **Event studies** | What price did after each event vs an all-bars baseline. Statistics, not P&L: no costs, no fills, no sizing. | `scorecard.json`, `report.md` |

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

## 1b. Footprint + DOM (`/footprint`)

The auction *inside* each candle, built from every trade and who was aggressive.

- **Cells:** `bid × ask` per price row. Left/red = sellers hitting the bid, right/green = buyers lifting the offer.
  Switch to **Delta** (ask − bid) or **Vol** view.
- **Diagonal imbalances** (default 3×) light up bold. **3+ stacked** become zones that extend right as S/R.
- **POC** per candle boxed in gold. **Unfinished auctions** (both sides traded at the extreme) get a gold dot.
- Under each candle: time, **delta**, **volume**. Right edge: session volume profile.
- **DOM ladder:** resting bids/asks (walls ≥3× avg go bold), recent 15s aggression per price (Sells / Buys
  columns), session traded volume behind the price column, last trade boxed.
- **Time & sales** with a min-size filter. Top-5% prints get highlighted.
- Controls: bar size (1m–1h), row size (ticks), imbalance ratio. Drag to pan, wheel = row height,
  shift+wheel = column width, double-click = snap back to live.

**Data feeds** (needs aggressor-tagged trades, which Yahoo doesn't have):

| Market | Feed | Cost | Setup |
|---|---|---|---|
| BTC, ETH | Kraken public websocket | free | nothing, just works |
| ES, NQ, MES, MNQ, YM, CL, GC | Databento (CME Globex `trades` + `mbp-10`) | usage-based | `pip install databento`, `export DATABENTO_API_KEY=...` |
| anything | **Sim** button | free | synthetic tape for testing, always badged **SIM** |

On connect it backfills the last ~2h so the chart isn't empty. Without a key, Live mode tells you so.
It never falls back to fake data on its own.

> **Status: the CME/Databento path is NOT verified against the real feed yet.** It's only been tested
> against Databento's record classes with constructed data. Don't trust the CME footprint/DOM until
> `verify_databento` prints `CLEAN` on real NQ data.

**CME data path (Databento):** history comes from `trades`, then *everything* live (prints + book) comes from
`mbp-10` alone, so the footprint and DOM can't drift apart in time. Book updates are only shown at the end of
each exchange event (`F_LAST`), crossed books are rejected, and the DOM is labeled **L2 · top 10** because
that's all MBP-10 carries. **Before trusting it, run the self-check once you have a key:**

```bash
DATABENTO_API_KEY=... python -m ofcore.verify_databento NQ --minutes 3
```

It replays both streams and confirms every live print matches the trades feed (time, sequence, price, size,
aggressor side), the book is never crossed, timestamps don't go backwards, and buys print at the ask / sells at
the bid. Prints `CLEAN` or tells you exactly what to look at.

## 2. Pine pack (`pine/`)

Open TradingView → Pine Editor → paste → *Add to chart*. All are Pine v6.

| File | What it does |
|---|---|
| `of_auction_profile.pine` | **Estimated** composite VP on the right edge (bar volume spread over its range), prior-session POC + VA boxes, **naked POCs that extend until revisited**, *possible* poor high/low flags (heuristic), developing POC/VA, RTH initial balance. Alert: near naked POC. |
| `of_delta_cvd.pine` | **EST. DELTA / EST. CVD** from lower-timeframe candle direction (not bid/ask). Readout shows the source (`estimated intrabar` vs `fallback estimate`, fallback bars drawn gray). `Confirmed signals only` (default on) gates alerts; divergence markers sit on the bar where they were confirmed. CVD candles / line / delta bars, weekly reset, **CVD divergences**, **absorption** markers. Alerts for all. |
| `of_vwap_ema_rvol.pine` | **RTH VWAP** (09:30–16:00 NY, frozen after the close, session/time zone configurable) + weekly/monthly/quarterly anchored VWAPs with σ bands (clean breaks), EMA stack, RVOL candle highlight, readout table. Handles no-volume FX feeds. |
| `of_gamma_levels.pine` | **Estimated** gamma: paste `zg;call;put;majors;proxy;calc_time` from the dashboard/scanner. Shows proxy, calculation time, age and **STALE**; neutral regime wording; never paints levels onto bars before they were calculated. Wall alerts split into approach / touch / reject / break / acceptance (confirmed bars). |
| `of_qqq_strike_map.pine` | QQQ strike grid + your key levels (call/put wall, Γ/λ zones) drawn on NQ/MNQ at the **live NQ/QQQ ratio** (held overnight while QQQ is closed). Levels are typed in from your GEX source or the scanner, not computed. Alerts: wall touch/cross, key-level touch (confirmed bars). |

## 3. Scanner

```bash
python -m scanner.scan --dry-run          # look, don't send
python -m scanner.scan                    # send new setups
python -m scanner.scan --loop 60          # every hour
python -m scanner.scan --symbols ES,NQ,6E --tf 4h
```

Set `DISCORD_WEBHOOK_URL` and/or `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`. Tune `scanner/config.toml`.

Alerts are **events**: a setup alerts on the closed bar where it switches on (the still-forming candle is
ignored). If it stays on, there's no repeat. If it turns off and fires again later (accepted, fell back in,
accepted again), that's a new alert. On GitHub the "already alerted" memory lives on a `scanner-state` branch.
It also runs on GitHub every 2h (Sun–Fri) via `.github/workflows/scanner.yml`. Just add the `DISCORD_WEBHOOK_URL` repo secret.

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

## Research: which signals deserve to influence a trade?

```bash
python -m research.events all        # replay -> outcomes -> study (needs the data snapshot below)
```

1. **Data snapshot.** `.github/workflows/research-data.yml` downloads real NQ/MNQ/ES/MES bars from Yahoo
   (1m ≈ 4 weeks, 5m ≈ 10 weeks, 1h ≈ 2.4 years) and freezes them on the `research-data` branch. Pull it with
   `git fetch origin research-data` and extract `data/market/yahoo/`. Yahoo's `=F` contracts aren't
   back-adjusted and the mini/micro roll on different days, so bars in roll windows or where NQ≠MNQ / ES≠MES are
   flagged `price: degraded` and any event whose outcome window touches one is excluded (and counted).
2. **Replay.** Bar by bar, the detector sees only data up to that bar, exactly as the live scanner would. An event
   is the bar a setup switches on. Context (RTH/weekly VWAP, RVOL, EMA stack, auction state) is stored with it.
   **Gamma is never replayed**: there is no historical options chain, so gamma setups are `UNTESTED` and the
   live scanner logs them going forward (`data/research/events/live/`).
3. **Outcomes.** Entry = event bar close. +5/15/30/60/240 min: forward return, MFE/MAE, time to a 0.5-ATR
   favorable/adverse move, from the finest data available (1m → 5m → 1h; never interpolated).
4. **Study.** Direction-signed return in ATR units vs the **all-bars baseline** for the same symbol/session.
   Status is judged at one **pre-registered** horizon (30m for 5m events, 4h for 1h events) with a
   session-clustered bootstrap CI and **both chronological halves must agree**:
   `INSUFFICIENT_SAMPLE` (<30) / `WEAK` / `MIXED` / `PROMISING` / `INVALIDATED`. Nothing is called an edge.
5. **Leakage tests** (`tests/test_research.py`) rebuild every event from data cut at its own bar and require a
   byte-identical record; they were checked by planting look-ahead bugs, which they caught.

Outputs: `data/research/events/scorecard.json`, `report.md`, `details.json`, `replay/*.jsonl`.

## Honest notes

- **Delta/CVD in the dashboard + scanner is estimated** from where each bar closed in its range
  (Yahoo has no bid/ask split). It's directionally solid on swing timeframes but it isn't a footprint.
  The Pine delta script uses intrabars, so trust that one more. For true footprint/bid-ask data you'd plug a
  feed like Rithmic / CQG / Databento into `ofcore/data.py`.
- **Gamma is estimated, not observed.** It comes from the ETF proxy's options chain (SPY→ES, QQQ→NQ, IWM→RTY, GLD→GC, USO→CL, FXE→6E...),
  scaled to the futures price. Index proxies are good. FX/commodity ETF proxies are thin, so treat them as rough context.
- Yahoo intraday is delayed and capped (~730 days of 1h). Fine for swing work, not for execution.
- **Don't expose the dashboard publicly.** It binds to localhost. If you run it on a server, put it behind
  Tailscale / Cloudflare Access, or at minimum set `OF_TOKEN=...` and open it once with `?token=...`.
- Not financial advice, it's a tool. Size your risk.

## Layout

```
ofcore/      engine: data, indicators, profile, auction read, gamma, setups, footprint, live feeds
dashboard/   FastAPI + static frontend (lightweight-charts vendored, Apache-2.0)
pine/        TradingView indicators
scanner/     CLI scanner + config (scheduled run: .github/workflows/scanner.yml)
research/    point-in-time replay, outcomes, event study, scorecard
data/        validation reports, research events + scorecard (market snapshot lives on `research-data`)
tests/       pytest (runs offline: demo data + constructed records, no network)
```
