# Event study report

Generated 2026-10-05T17:42Z from yahoo finance (yfinance), delayed snapshot fetched 2026-10-05T17:14Z. **Delta is estimated, gamma is unavailable historically, no tick-level footprint.** This is an event study, not a P&L backtest: no costs, no fills.

## Method (fixed before results)

- **primary_horizon_min**: {'5m': 30, '1h': 240}
- **min_sample**: 30
- **baseline**: all bars, same symbol/tf/session
- **metric**: direction-signed forward return in ATR units
- **ci**: session-clustered bootstrap 95%
- **oos**: both chronological halves must agree
- **tests_run**: 71
- **expected_false_positives_at_5pct**: 3.6
- **note**: NQ/MNQ and ES/MES are the same markets: they are not independent confirmations
- **status_note**: MIXED vs WEAK: halves disagreeing by > 0.05 ATR counts as MIXED. That threshold is small next to 4h noise, so most MIXED rows are noise too. Both mean: no reliable evidence. Only PROMISING / INVALIDATED are claims, and with this many tests a few of those are expected by chance.

## Signals (primary horizon)

| signal | sym | tf | n | sessions | hit | baseline | edge (ATR) | edge 95% CI | halves | MFE/MAE (ATR) | status |
|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|
| accept_above | NQ | 5m | 31 | 12 | 0.42 | 0.51 | +0.109 | [-0.397, +0.921] | +0.202 / +0.021 | 1.17 / 1.03 | **WEAK** |
| accept_above | NQ | 1h | 134 | 109 | 0.48 | 0.53 | -0.191 | [-0.552, +0.099] | -0.069 / -0.314 | 0.85 / 1.14 | **WEAK** |
| accept_above | MNQ | 5m | 28 | 11 | 0.43 | 0.51 | -0.014 | [-0.466, +0.952] | +0.549 / -0.577 | 1.11 / 1.05 | **INSUFFICIENT_SAMPLE** |
| accept_above | MNQ | 1h | 124 | 103 | 0.52 | 0.54 | -0.065 | [-0.404, +0.228] | +0.148 / -0.279 | 0.92 / 1.00 | **MIXED** |
| accept_above | ES | 5m | 20 | 11 | 0.65 | 0.48 | +0.431 | [-0.519, +1.633] | +0.553 / +0.309 | 1.43 / 1.45 | **INSUFFICIENT_SAMPLE** |
| accept_above | ES | 1h | 134 | 108 | 0.52 | 0.53 | +0.006 | [-0.230, +0.254] | +0.207 / -0.194 | 0.96 / 1.07 | **MIXED** |
| accept_above | MES | 5m | 20 | 10 | 0.45 | 0.48 | +0.259 | [-0.651, +1.293] | +0.303 / +0.215 | 1.23 / 1.48 | **INSUFFICIENT_SAMPLE** |
| accept_above | MES | 1h | 139 | 111 | 0.53 | 0.54 | +0.067 | [-0.214, +0.373] | +0.188 / -0.053 | 1.02 / 1.04 | **MIXED** |
| accept_below | NQ | 5m | 24 | 11 | 0.67 | 0.49 | +0.834 | [-0.061, +1.674] | +0.764 / +0.904 | 1.86 / 1.23 | **INSUFFICIENT_SAMPLE** |
| accept_below | NQ | 1h | 102 | 85 | 0.48 | 0.46 | +0.034 | [-0.259, +0.331] | -0.011 / +0.080 | 1.25 / 1.06 | **MIXED** |
| accept_below | MNQ | 5m | 27 | 11 | 0.70 | 0.49 | +0.676 | [+0.049, +1.284] | +0.865 / +0.502 | 1.66 / 1.10 | **INSUFFICIENT_SAMPLE** |
| accept_below | MNQ | 1h | 96 | 80 | 0.53 | 0.46 | +0.240 | [-0.053, +0.521] | +0.407 / +0.073 | 1.37 / 0.99 | **WEAK** |
| accept_below | ES | 5m | 31 | 13 | 0.45 | 0.49 | -0.118 | [-0.567, +0.477] | -0.329 / +0.080 | 1.23 / 1.28 | **MIXED** |
| accept_below | ES | 1h | 99 | 85 | 0.46 | 0.46 | +0.247 | [-0.088, +0.558] | +0.267 / +0.227 | 1.37 / 1.02 | **WEAK** |
| accept_below | MES | 5m | 40 | 14 | 0.38 | 0.49 | -0.155 | [-0.470, +0.238] | -0.107 / -0.204 | 1.19 / 1.24 | **WEAK** |
| accept_below | MES | 1h | 101 | 87 | 0.47 | 0.46 | +0.322 | [-0.017, +0.630] | +0.223 / +0.418 | 1.48 / 1.00 | **WEAK** |
| lookabove_fail | NQ | 5m | 51 | 13 | 0.37 | 0.49 | -0.502 | [-1.001, +0.017] | -0.399 / -0.601 | 1.10 / 1.48 | **WEAK** |
| lookabove_fail | NQ | 1h | 280 | 185 | 0.45 | 0.46 | +0.037 | [-0.151, +0.237] | +0.061 / +0.012 | 1.24 / 1.04 | **WEAK** |
| lookabove_fail | MNQ | 5m | 48 | 11 | 0.33 | 0.49 | -0.438 | [-0.863, +0.063] | -0.505 / -0.372 | 1.28 / 1.48 | **WEAK** |
| lookabove_fail | MNQ | 1h | 276 | 186 | 0.47 | 0.46 | +0.032 | [-0.171, +0.235] | -0.013 / +0.076 | 1.22 / 1.06 | **MIXED** |
| lookabove_fail | ES | 5m | 52 | 14 | 0.42 | 0.50 | +0.121 | [-0.167, +0.601] | +0.270 / -0.027 | 1.52 / 0.99 | **MIXED** |
| lookabove_fail | ES | 1h | 317 | 202 | 0.47 | 0.46 | +0.156 | [-0.045, +0.384] | +0.240 / +0.072 | 1.45 / 1.08 | **WEAK** |
| lookabove_fail | MES | 5m | 43 | 14 | 0.37 | 0.50 | +0.096 | [-0.210, +0.595] | +0.398 / -0.193 | 1.42 / 1.01 | **MIXED** |
| lookabove_fail | MES | 1h | 310 | 196 | 0.45 | 0.46 | +0.098 | [-0.121, +0.343] | +0.106 / +0.090 | 1.41 / 1.09 | **WEAK** |
| lookbelow_fail | NQ | 5m | 50 | 14 | 0.46 | 0.51 | -0.250 | [-0.921, +0.216] | -0.445 / -0.055 | 1.20 / 1.53 | **WEAK** |
| lookbelow_fail | NQ | 1h | 251 | 167 | 0.50 | 0.54 | -0.045 | [-0.231, +0.155] | +0.073 / -0.163 | 0.96 / 1.20 | **MIXED** |
| lookbelow_fail | MNQ | 5m | 52 | 14 | 0.44 | 0.51 | -0.264 | [-0.939, +0.337] | -0.585 / +0.058 | 1.16 / 1.53 | **MIXED** |
| lookbelow_fail | MNQ | 1h | 240 | 157 | 0.52 | 0.54 | -0.017 | [-0.222, +0.183] | +0.013 / -0.048 | 0.98 / 1.15 | **WEAK** |
| lookbelow_fail | ES | 5m | 77 | 13 | 0.55 | 0.48 | +0.029 | [-0.258, +0.254] | -0.031 / +0.087 | 1.28 / 1.27 | **MIXED** |
| lookbelow_fail | ES | 1h | 245 | 178 | 0.52 | 0.53 | -0.115 | [-0.308, +0.081] | +0.062 / -0.289 | 0.97 / 1.24 | **MIXED** |
| lookbelow_fail | MES | 5m | 85 | 15 | 0.55 | 0.48 | +0.038 | [-0.174, +0.355] | +0.037 / +0.038 | 1.10 / 1.28 | **WEAK** |
| lookbelow_fail | MES | 1h | 245 | 176 | 0.51 | 0.54 | -0.085 | [-0.279, +0.098] | +0.062 / -0.231 | 0.96 / 1.19 | **MIXED** |
| balance_edge_high | NQ | 5m | 0 | 0 | — | — | — | [—, —] | — / — | — / — | **INSUFFICIENT_SAMPLE** |
| balance_edge_high | NQ | 1h | 11 | 10 | 0.36 | 0.46 | -0.212 | [-0.722, +0.376] | -0.102 / -0.303 | 0.67 / 0.98 | **INSUFFICIENT_SAMPLE** |
| balance_edge_high | MNQ | 5m | 0 | 0 | — | — | — | [—, —] | — / — | — / — | **INSUFFICIENT_SAMPLE** |
| balance_edge_high | MNQ | 1h | 12 | 11 | 0.25 | 0.46 | -0.597 | [-1.027, +0.002] | -0.852 / -0.342 | 0.61 / 1.15 | **INSUFFICIENT_SAMPLE** |
| balance_edge_high | ES | 5m | 5 | 2 | 0.20 | 0.48 | +0.061 | [-0.641, +2.865] | -0.644 / +0.530 | 1.60 / 1.34 | **INSUFFICIENT_SAMPLE** |
| balance_edge_high | ES | 1h | 23 | 19 | 0.43 | 0.46 | -0.261 | [-0.724, +0.253] | -0.175 / -0.339 | 0.87 / 1.27 | **INSUFFICIENT_SAMPLE** |
| balance_edge_high | MES | 5m | 2 | 1 | 0.00 | 0.48 | -0.544 | [-0.544, -0.544] | -0.402 / -0.686 | 1.72 / 0.90 | **INSUFFICIENT_SAMPLE** |
| balance_edge_high | MES | 1h | 26 | 19 | 0.50 | 0.46 | -0.007 | [-0.490, +0.447] | -0.123 / +0.109 | 1.17 / 1.14 | **INSUFFICIENT_SAMPLE** |
| balance_edge_low | NQ | 5m | 0 | 0 | — | — | — | [—, —] | — / — | — / — | **INSUFFICIENT_SAMPLE** |
| balance_edge_low | NQ | 1h | 9 | 6 | 0.56 | 0.53 | +0.047 | [-2.683, +1.932] | -0.174 / +0.223 | 1.70 / 2.06 | **INSUFFICIENT_SAMPLE** |
| balance_edge_low | MNQ | 5m | 0 | 0 | — | — | — | [—, —] | — / — | — / — | **INSUFFICIENT_SAMPLE** |
| balance_edge_low | MNQ | 1h | 13 | 9 | 0.31 | 0.54 | -0.523 | [-1.854, +0.708] | -0.568 / -0.484 | 1.10 / 2.05 | **INSUFFICIENT_SAMPLE** |
| balance_edge_low | ES | 5m | 0 | 0 | — | — | — | [—, —] | — / — | — / — | **INSUFFICIENT_SAMPLE** |
| balance_edge_low | ES | 1h | 10 | 9 | 0.60 | 0.54 | +0.471 | [-0.232, +1.072] | +0.277 / +0.666 | 1.15 / 1.04 | **INSUFFICIENT_SAMPLE** |
| balance_edge_low | MES | 5m | 0 | 0 | — | — | — | [—, —] | — / — | — / — | **INSUFFICIENT_SAMPLE** |
| balance_edge_low | MES | 1h | 8 | 8 | 0.75 | 0.54 | +0.936 | [+0.081, +1.841] | +0.864 / +1.009 | 1.41 / 0.92 | **INSUFFICIENT_SAMPLE** |
| naked_poc | NQ | 5m | 8 | 7 | 0.38 | 0.50 | -0.644 | [-1.507, +0.167] | -0.844 / -0.444 | 0.81 / 1.35 | **INSUFFICIENT_SAMPLE** |
| naked_poc | NQ | 1h | 139 | 112 | 0.50 | 0.50 | -0.074 | [-0.350, +0.172] | +0.003 / -0.151 | 0.89 / 1.00 | **MIXED** |
| naked_poc | MNQ | 5m | 11 | 10 | 0.18 | 0.50 | -0.626 | [-1.132, -0.075] | -0.541 / -0.696 | 0.86 / 1.33 | **INSUFFICIENT_SAMPLE** |
| naked_poc | MNQ | 1h | 139 | 118 | 0.55 | 0.50 | -0.012 | [-0.224, +0.185] | -0.008 / -0.016 | 0.89 / 0.92 | **WEAK** |
| naked_poc | ES | 5m | 7 | 7 | 0.43 | 0.49 | +0.489 | [-0.461, +1.477] | +1.469 / -0.246 | 1.36 / 1.32 | **INSUFFICIENT_SAMPLE** |
| naked_poc | ES | 1h | 129 | 107 | 0.50 | 0.50 | -0.001 | [-0.246, +0.252] | -0.191 / +0.186 | 0.98 / 0.91 | **MIXED** |
| naked_poc | MES | 5m | 10 | 7 | 0.20 | 0.49 | -0.241 | [-1.372, +1.237] | +0.915 / -1.397 | 1.20 / 1.69 | **INSUFFICIENT_SAMPLE** |
| naked_poc | MES | 1h | 132 | 110 | 0.54 | 0.50 | +0.048 | [-0.176, +0.265] | -0.166 / +0.263 | 0.97 / 0.86 | **MIXED** |
| cvd_div_bullish | NQ | 5m | 187 | 34 | 0.53 | 0.51 | -0.004 | [-0.244, +0.253] | +0.097 / -0.104 | 1.37 / 1.29 | **MIXED** |
| cvd_div_bullish | NQ | 1h | 183 | 153 | 0.46 | 0.53 | -0.298 | [-0.593, -0.012] | -0.244 / -0.352 | 1.08 / 1.60 | **WEAK** |
| cvd_div_bullish | MNQ | 5m | 181 | 34 | 0.52 | 0.51 | +0.055 | [-0.207, +0.330] | +0.108 / +0.003 | 1.35 / 1.23 | **WEAK** |
| cvd_div_bullish | MNQ | 1h | 176 | 149 | 0.44 | 0.53 | -0.349 | [-0.647, -0.042] | -0.301 / -0.398 | 1.08 / 1.65 | **INVALIDATED** |
| cvd_div_bullish | ES | 5m | 202 | 34 | 0.51 | 0.49 | +0.128 | [-0.099, +0.369] | +0.253 / +0.003 | 1.35 / 1.27 | **WEAK** |
| cvd_div_bullish | ES | 1h | 173 | 154 | 0.57 | 0.53 | +0.135 | [-0.168, +0.408] | +0.005 / +0.262 | 1.29 / 1.36 | **WEAK** |
| cvd_div_bullish | MES | 5m | 203 | 35 | 0.49 | 0.48 | +0.013 | [-0.193, +0.234] | +0.124 / -0.096 | 1.23 / 1.32 | **MIXED** |
| cvd_div_bullish | MES | 1h | 174 | 157 | 0.56 | 0.54 | +0.076 | [-0.184, +0.358] | +0.066 / +0.087 | 1.22 / 1.35 | **WEAK** |
| cvd_div_bearish | NQ | 5m | 186 | 35 | 0.54 | 0.49 | +0.112 | [-0.115, +0.349] | +0.411 / -0.186 | 1.38 / 1.15 | **MIXED** |
| cvd_div_bearish | NQ | 1h | 213 | 179 | 0.46 | 0.47 | -0.067 | [-0.279, +0.163] | -0.242 / +0.107 | 1.18 / 1.09 | **MIXED** |
| cvd_div_bearish | MNQ | 5m | 187 | 35 | 0.53 | 0.49 | +0.088 | [-0.083, +0.278] | +0.195 / -0.018 | 1.38 / 1.27 | **MIXED** |
| cvd_div_bearish | MNQ | 1h | 206 | 171 | 0.46 | 0.47 | -0.010 | [-0.250, +0.212] | -0.131 / +0.110 | 1.23 / 1.05 | **MIXED** |
| cvd_div_bearish | ES | 5m | 193 | 35 | 0.46 | 0.49 | -0.075 | [-0.292, +0.190] | +0.057 / -0.205 | 1.30 / 1.28 | **MIXED** |
| cvd_div_bearish | ES | 1h | 238 | 200 | 0.51 | 0.46 | +0.123 | [-0.096, +0.330] | +0.174 / +0.071 | 1.30 / 0.97 | **WEAK** |
| cvd_div_bearish | MES | 5m | 196 | 35 | 0.46 | 0.49 | -0.085 | [-0.277, +0.145] | +0.020 / -0.189 | 1.26 / 1.24 | **MIXED** |
| cvd_div_bearish | MES | 1h | 227 | 185 | 0.51 | 0.46 | +0.221 | [-0.005, +0.467] | +0.416 / +0.027 | 1.31 / 0.94 | **WEAK** |
| vwap_pullback_long | NQ | 5m | 94 | 17 | 0.50 | 0.51 | -0.095 | [-0.255, +0.113] | -0.081 / -0.108 | 1.12 / 1.27 | **WEAK** |
| vwap_pullback_long | NQ | 1h | 348 | 170 | 0.53 | 0.54 | +0.030 | [-0.143, +0.210] | -0.082 / +0.141 | 1.08 / 1.21 | **MIXED** |
| vwap_pullback_long | MNQ | 5m | 106 | 17 | 0.53 | 0.51 | -0.064 | [-0.319, +0.204] | -0.370 / +0.243 | 1.18 / 1.26 | **MIXED** |
| vwap_pullback_long | MNQ | 1h | 341 | 169 | 0.52 | 0.54 | -0.001 | [-0.178, +0.177] | -0.099 / +0.097 | 1.06 / 1.21 | **MIXED** |
| vwap_pullback_long | ES | 5m | 108 | 18 | 0.46 | 0.49 | -0.156 | [-0.503, +0.197] | -0.053 / -0.258 | 1.13 / 1.44 | **WEAK** |
| vwap_pullback_long | ES | 1h | 392 | 193 | 0.58 | 0.53 | +0.061 | [-0.119, +0.234] | -0.013 / +0.134 | 1.13 / 1.21 | **MIXED** |
| vwap_pullback_long | MES | 5m | 124 | 19 | 0.41 | 0.48 | -0.306 | [-0.653, +0.076] | -0.095 / -0.518 | 1.01 / 1.54 | **WEAK** |
| vwap_pullback_long | MES | 1h | 364 | 184 | 0.56 | 0.54 | +0.004 | [-0.176, +0.182] | +0.048 / -0.041 | 1.10 / 1.25 | **WEAK** |
| vwap_pullback_short | NQ | 5m | 113 | 20 | 0.46 | 0.49 | -0.155 | [-0.432, +0.095] | -0.092 / -0.216 | 1.20 / 1.29 | **WEAK** |
| vwap_pullback_short | NQ | 1h | 270 | 142 | 0.47 | 0.46 | +0.061 | [-0.156, +0.294] | +0.106 / +0.017 | 1.36 / 1.13 | **WEAK** |
| vwap_pullback_short | MNQ | 5m | 97 | 18 | 0.46 | 0.49 | -0.234 | [-0.483, +0.015] | -0.036 / -0.428 | 1.12 / 1.38 | **WEAK** |
| vwap_pullback_short | MNQ | 1h | 267 | 141 | 0.44 | 0.46 | -0.027 | [-0.256, +0.191] | +0.077 / -0.130 | 1.33 / 1.15 | **MIXED** |
| vwap_pullback_short | ES | 5m | 98 | 17 | 0.51 | 0.49 | +0.225 | [-0.158, +0.608] | +0.020 / +0.430 | 1.67 / 1.35 | **WEAK** |
| vwap_pullback_short | ES | 1h | 272 | 143 | 0.45 | 0.46 | -0.030 | [-0.253, +0.204] | -0.059 / -0.001 | 1.32 / 1.22 | **WEAK** |
| vwap_pullback_short | MES | 5m | 96 | 17 | 0.50 | 0.49 | +0.164 | [-0.194, +0.552] | -0.010 / +0.339 | 1.62 / 1.36 | **MIXED** |
| vwap_pullback_short | MES | 1h | 264 | 135 | 0.46 | 0.46 | -0.052 | [-0.254, +0.166] | -0.162 / +0.057 | 1.29 / 1.20 | **MIXED** |
| rvol | NQ | 5m | 371 | 34 | 0.51 | 0.50 | -0.002 | [-0.179, +0.151] | +0.064 / -0.068 | 1.32 / 1.28 | **MIXED** |
| rvol | NQ | 1h | 330 | 221 | 0.50 | 0.50 | -0.028 | [-0.154, +0.103] | -0.104 / +0.048 | 1.07 / 1.05 | **MIXED** |
| rvol | MNQ | 5m | 335 | 32 | 0.50 | 0.50 | +0.011 | [-0.176, +0.187] | -0.051 / +0.072 | 1.30 / 1.30 | **MIXED** |
| rvol | MNQ | 1h | 314 | 226 | 0.52 | 0.49 | +0.023 | [-0.125, +0.171] | -0.073 / +0.120 | 1.06 / 1.01 | **MIXED** |
| rvol | ES | 5m | 381 | 34 | 0.45 | 0.49 | -0.081 | [-0.271, +0.094] | +0.029 / -0.190 | 1.33 / 1.38 | **MIXED** |
| rvol | ES | 1h | 348 | 237 | 0.51 | 0.49 | -0.012 | [-0.153, +0.127] | -0.067 / +0.042 | 1.07 / 1.06 | **MIXED** |
| rvol | MES | 5m | 459 | 35 | 0.48 | 0.49 | -0.014 | [-0.151, +0.114] | +0.046 / -0.073 | 1.25 / 1.27 | **MIXED** |
| rvol | MES | 1h | 376 | 244 | 0.51 | 0.49 | -0.016 | [-0.149, +0.110] | -0.066 / +0.033 | 1.11 / 1.02 | **MIXED** |

Untested: call_wall, gamma_flip_cross, gamma_flip_near, put_wall (no point-in-time options history).

## Combinations (pre-registered)

- **cvd_div_bearish + below RTH VWAP + bear EMA stack** NQ 5m: n=2, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bearish + below RTH VWAP + bear EMA stack** NQ 1h: n=4, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bearish + below RTH VWAP + bear EMA stack** MNQ 5m: n=1, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bearish + below RTH VWAP + bear EMA stack** MNQ 1h: n=5, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bearish + below RTH VWAP + bear EMA stack** ES 5m: n=6, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bearish + below RTH VWAP + bear EMA stack** ES 1h: n=2, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bearish + below RTH VWAP + bear EMA stack** MES 5m: n=7, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bearish + below RTH VWAP + bear EMA stack** MES 1h: n=2, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bullish + above RTH VWAP + bull EMA stack** NQ 5m: n=5, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bullish + above RTH VWAP + bull EMA stack** NQ 1h: n=3, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bullish + above RTH VWAP + bull EMA stack** MNQ 5m: n=5, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bullish + above RTH VWAP + bull EMA stack** MNQ 1h: n=3, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bullish + above RTH VWAP + bull EMA stack** ES 5m: n=6, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bullish + above RTH VWAP + bull EMA stack** ES 1h: n=2, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bullish + above RTH VWAP + bull EMA stack** MES 5m: n=6, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **cvd_div_bullish + above RTH VWAP + bull EMA stack** MES 1h: n=2, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookabove_fail + high RVOL + below weekly VWAP** NQ 5m: n=2, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookabove_fail + high RVOL + below weekly VWAP** NQ 1h: n=16, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookabove_fail + high RVOL + below weekly VWAP** MNQ 5m: n=1, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookabove_fail + high RVOL + below weekly VWAP** MNQ 1h: n=14, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookabove_fail + high RVOL + below weekly VWAP** ES 5m: n=2, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookabove_fail + high RVOL + below weekly VWAP** ES 1h: n=16, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookabove_fail + high RVOL + below weekly VWAP** MES 5m: n=4, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookabove_fail + high RVOL + below weekly VWAP** MES 1h: n=19, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookbelow_fail + high RVOL + above weekly VWAP** NQ 5m: n=3, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookbelow_fail + high RVOL + above weekly VWAP** NQ 1h: n=13, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookbelow_fail + high RVOL + above weekly VWAP** MNQ 5m: n=3, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookbelow_fail + high RVOL + above weekly VWAP** MNQ 1h: n=13, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookbelow_fail + high RVOL + above weekly VWAP** ES 5m: n=1, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookbelow_fail + high RVOL + above weekly VWAP** ES 1h: n=14, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookbelow_fail + high RVOL + above weekly VWAP** MES 5m: n=1, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **lookbelow_fail + high RVOL + above weekly VWAP** MES 1h: n=20, edge=— ATR → **INSUFFICIENT_SAMPLE**
- **gamma flip + RTH VWAP rejection + high RVOL**  : n=0, edge=— ATR → **UNTESTED**

Rationale: _cvd_div_bearish + below RTH VWAP + bear EMA stack_: fading aggression at a high while the session's value (RTH VWAP) and trend already point down; _cvd_div_bullish + above RTH VWAP + bull EMA stack_: mirror of the above; _lookabove_fail + high RVOL + below weekly VWAP_: a failed breakout on heavy participation against the weekly value area; _lookbelow_fail + high RVOL + above weekly VWAP_: mirror of the above; _gamma flip + RTH VWAP rejection + high RVOL_: needs point-in-time gamma history, which doesn't exist yet

## Horizons and segments

- **accept_above NQ 5m** edge by horizon: 5m: +0.058, 15m: +0.015, 30m: +0.109, 60m: -0.167
- **accept_above NQ 1h** edge by horizon: 60m: +0.025, 240m: -0.191
  - by session: ETH n=97 edge=-0.192; RTH n=37 edge=-0.190
- **accept_above MNQ 1h** edge by horizon: 60m: +0.126, 240m: -0.065
  - by session: ETH n=85 edge=-0.082; RTH n=39 edge=-0.029
- **accept_above ES 1h** edge by horizon: 60m: -0.034, 240m: +0.006
  - by session: ETH n=97 edge=-0.066; RTH n=37 edge=+0.197
- **accept_above MES 1h** edge by horizon: 60m: +0.026, 240m: +0.067
  - by session: ETH n=100 edge=-0.012; RTH n=39 edge=+0.269
- **accept_below NQ 1h** edge by horizon: 60m: +0.001, 240m: +0.034
- **accept_below MNQ 1h** edge by horizon: 60m: +0.065, 240m: +0.240
  - by rvol_bucket: high n=33 edge=+0.043; low n=63 edge=+0.343
- **accept_below ES 5m** edge by horizon: 5m: -0.039, 15m: -0.234, 30m: -0.118, 60m: -0.009
- **accept_below ES 1h** edge by horizon: 60m: -0.057, 240m: +0.247
  - by rvol_bucket: high n=39 edge=+0.086; low n=60 edge=+0.351
- **accept_below MES 5m** edge by horizon: 5m: -0.030, 15m: -0.285, 30m: -0.155, 60m: -0.234, 240m: -0.098
- **accept_below MES 1h** edge by horizon: 60m: +0.040, 240m: +0.322
  - by rvol_bucket: high n=40 edge=+0.174; low n=61 edge=+0.419
- **lookabove_fail NQ 5m** edge by horizon: 5m: -0.061, 15m: -0.204, 30m: -0.502, 60m: -0.423, 240m: -0.186
- **lookabove_fail NQ 1h** edge by horizon: 60m: +0.046, 240m: +0.037
  - by session: ETH n=176 edge=-0.071; RTH n=104 edge=+0.218
  - by vs_rth_vwap: above n=142 edge=-0.109; below n=138 edge=+0.187
  - by rvol_bucket: high n=42 edge=-0.128; low n=238 edge=+0.066
- **lookabove_fail MNQ 5m** edge by horizon: 5m: -0.023, 15m: -0.114, 30m: -0.438, 60m: -0.340, 240m: +0.052
- **lookabove_fail MNQ 1h** edge by horizon: 60m: +0.004, 240m: +0.032
  - by session: ETH n=170 edge=-0.062; RTH n=106 edge=+0.182
  - by vs_rth_vwap: above n=136 edge=-0.110; below n=140 edge=+0.169
  - by rvol_bucket: high n=47 edge=-0.106; low n=229 edge=+0.060
- **lookabove_fail ES 5m** edge by horizon: 5m: +0.211, 15m: +0.245, 30m: +0.121, 60m: -0.125, 240m: -0.064
- **lookabove_fail ES 1h** edge by horizon: 60m: -0.023, 240m: +0.156
  - by session: ETH n=207 edge=+0.053; RTH n=110 edge=+0.350
  - by vs_rth_vwap: above n=176 edge=+0.093; below n=141 edge=+0.234
  - by rvol_bucket: high n=48 edge=+0.061; low n=269 edge=+0.173
- **lookabove_fail MES 5m** edge by horizon: 5m: +0.216, 15m: +0.229, 30m: +0.096, 60m: -0.169, 240m: +0.177
- **lookabove_fail MES 1h** edge by horizon: 60m: -0.023, 240m: +0.098
  - by session: ETH n=198 edge=+0.035; RTH n=112 edge=+0.209
  - by vs_rth_vwap: above n=163 edge=+0.153; below n=147 edge=+0.037
  - by rvol_bucket: high n=61 edge=+0.045; low n=249 edge=+0.111
- **lookbelow_fail NQ 5m** edge by horizon: 5m: +0.117, 15m: +0.040, 30m: -0.250, 60m: -0.529, 240m: -0.302
- **lookbelow_fail NQ 1h** edge by horizon: 5m: +0.051, 30m: -0.040, 60m: -0.061, 240m: -0.045
  - by session: ETH n=152 edge=-0.039; RTH n=99 edge=-0.056
  - by vs_rth_vwap: above n=146 edge=+0.037; below n=105 edge=-0.160
  - by rvol_bucket: high n=52 edge=+0.007; low n=199 edge=-0.059
- **lookbelow_fail MNQ 5m** edge by horizon: 5m: -0.023, 15m: -0.191, 30m: -0.264, 60m: -0.578, 240m: -0.754
- **lookbelow_fail MNQ 1h** edge by horizon: 60m: -0.025, 240m: -0.017
  - by session: ETH n=159 edge=-0.080; RTH n=81 edge=+0.106
  - by vs_rth_vwap: above n=135 edge=+0.113; below n=105 edge=-0.185
  - by rvol_bucket: high n=52 edge=-0.008; low n=188 edge=-0.020
- **lookbelow_fail ES 5m** edge by horizon: 5m: -0.043, 15m: +0.063, 30m: +0.029, 60m: +0.042, 240m: -0.591
  - by session: ETH n=40 edge=+0.306; RTH n=37 edge=-0.271
- **lookbelow_fail ES 1h** edge by horizon: 60m: -0.028, 240m: -0.115
  - by session: ETH n=164 edge=-0.136; RTH n=81 edge=-0.072
  - by vs_rth_vwap: above n=136 edge=-0.041; below n=109 edge=-0.206
  - by rvol_bucket: high n=55 edge=-0.467; low n=190 edge=-0.013
- **lookbelow_fail MES 5m** edge by horizon: 5m: -0.141, 15m: -0.107, 30m: +0.038, 60m: -0.040, 240m: -0.084
  - by session: ETH n=46 edge=+0.114; RTH n=39 edge=-0.052
- **lookbelow_fail MES 1h** edge by horizon: 5m: -0.030, 15m: -0.045, 30m: -0.058, 60m: -0.059, 240m: -0.085
  - by session: ETH n=162 edge=-0.117; RTH n=83 edge=-0.023
  - by vs_rth_vwap: above n=137 edge=+0.035; below n=108 edge=-0.237
  - by rvol_bucket: high n=64 edge=-0.187; low n=181 edge=-0.049
- **naked_poc NQ 1h** edge by horizon: 60m: -0.019, 240m: -0.074
  - by vs_rth_vwap: above n=76 edge=-0.353; below n=63 edge=+0.262
- **naked_poc MNQ 1h** edge by horizon: 60m: -0.013, 240m: -0.012
  - by vs_rth_vwap: above n=78 edge=-0.111; below n=61 edge=+0.114
- **naked_poc ES 1h** edge by horizon: 60m: -0.016, 240m: -0.001
  - by vs_rth_vwap: above n=77 edge=+0.008; below n=52 edge=-0.014
- **naked_poc MES 1h** edge by horizon: 60m: +0.009, 240m: +0.048
  - by vs_rth_vwap: above n=73 edge=+0.157; below n=59 edge=-0.087
- **cvd_div_bullish NQ 5m** edge by horizon: 5m: +0.091, 15m: +0.219, 30m: -0.004, 60m: +0.089, 240m: +0.343
  - by session: ETH n=144 edge=-0.048; RTH n=43 edge=+0.144
  - by vs_rth_vwap: above n=53 edge=-0.308; below n=134 edge=+0.116
  - by rvol_bucket: high n=53 edge=-0.412; low n=134 edge=+0.157
- **cvd_div_bullish NQ 1h** edge by horizon: 60m: -0.121, 240m: -0.298
  - by session: ETH n=133 edge=-0.076; RTH n=50 edge=-0.890
  - by rvol_bucket: high n=74 edge=+0.102; low n=109 edge=-0.570
- **cvd_div_bullish MNQ 5m** edge by horizon: 5m: +0.060, 15m: +0.151, 30m: +0.055, 60m: +0.138, 240m: +0.343
  - by session: ETH n=137 edge=+0.028; RTH n=44 edge=+0.138
  - by vs_rth_vwap: above n=52 edge=-0.116; below n=129 edge=+0.124
  - by rvol_bucket: high n=53 edge=+0.009; low n=128 edge=+0.074
- **cvd_div_bullish MNQ 1h** edge by horizon: 60m: -0.123, 240m: -0.349
  - by session: ETH n=127 edge=-0.079; RTH n=48 edge=-1.065
  - by rvol_bucket: high n=69 edge=+0.092; low n=107 edge=-0.634
- **cvd_div_bullish ES 5m** edge by horizon: 5m: +0.078, 15m: +0.135, 30m: +0.128, 60m: +0.045, 240m: -0.223
  - by session: ETH n=147 edge=+0.196; RTH n=55 edge=-0.053
  - by vs_rth_vwap: above n=47 edge=-0.055; below n=155 edge=+0.184
  - by rvol_bucket: high n=52 edge=+0.146; low n=150 edge=+0.122
- **cvd_div_bullish ES 1h** edge by horizon: 60m: -0.021, 240m: +0.135
  - by session: ETH n=124 edge=+0.237; RTH n=49 edge=-0.126
  - by rvol_bucket: high n=87 edge=+0.266; low n=86 edge=+0.002
- **cvd_div_bullish MES 5m** edge by horizon: 5m: -0.013, 15m: +0.028, 30m: +0.013, 60m: -0.018, 240m: +0.121
  - by session: ETH n=152 edge=+0.076; RTH n=51 edge=-0.174
  - by vs_rth_vwap: above n=46 edge=-0.364; below n=157 edge=+0.124
  - by rvol_bucket: high n=57 edge=-0.103; low n=146 edge=+0.059
- **cvd_div_bullish MES 1h** edge by horizon: 60m: -0.002, 240m: +0.076
  - by session: ETH n=126 edge=+0.170; RTH n=48 edge=-0.169
  - by rvol_bucket: high n=91 edge=+0.171; low n=83 edge=-0.027
- **cvd_div_bearish NQ 5m** edge by horizon: 5m: +0.080, 15m: +0.134, 30m: +0.112, 60m: +0.270, 240m: +0.521
  - by session: ETH n=147 edge=+0.092; RTH n=39 edge=+0.191
  - by vs_rth_vwap: above n=148 edge=+0.094; below n=38 edge=+0.184
  - by rvol_bucket: high n=33 edge=+0.276; low n=151 edge=+0.085
- **cvd_div_bearish NQ 1h** edge by horizon: 60m: -0.019, 240m: -0.067
  - by session: ETH n=177 edge=-0.156; RTH n=36 edge=+0.373
  - by vs_rth_vwap: above n=181 edge=-0.075; below n=32 edge=-0.018
  - by rvol_bucket: high n=35 edge=+0.049; low n=178 edge=-0.090
- **cvd_div_bearish MNQ 5m** edge by horizon: 5m: +0.108, 15m: +0.133, 30m: +0.088, 60m: +0.108, 240m: +0.265
  - by session: ETH n=144 edge=+0.085; RTH n=43 edge=+0.098
  - by vs_rth_vwap: above n=150 edge=+0.095; below n=37 edge=+0.058
  - by rvol_bucket: high n=31 edge=+0.212; low n=154 edge=+0.069
- **cvd_div_bearish MNQ 1h** edge by horizon: 60m: +0.003, 240m: -0.010
  - by session: ETH n=169 edge=-0.081; RTH n=37 edge=+0.315
  - by vs_rth_vwap: above n=173 edge=-0.008; below n=33 edge=-0.024
- **cvd_div_bearish ES 5m** edge by horizon: 5m: -0.017, 15m: +0.021, 30m: -0.075, 60m: +0.065, 240m: +0.255
  - by session: ETH n=146 edge=-0.036; RTH n=47 edge=-0.193
  - by vs_rth_vwap: above n=141 edge=-0.230; below n=52 edge=+0.346
  - by rvol_bucket: high n=36 edge=-0.043; low n=155 edge=-0.097
- **cvd_div_bearish ES 1h** edge by horizon: 60m: +0.025, 240m: +0.123
  - by session: ETH n=203 edge=+0.035; RTH n=35 edge=+0.629
  - by rvol_bucket: high n=36 edge=+0.352; low n=202 edge=+0.082
- **cvd_div_bearish MES 5m** edge by horizon: 5m: +0.009, 15m: -0.020, 30m: -0.085, 60m: -0.132, 240m: +0.042
  - by session: ETH n=150 edge=-0.087; RTH n=46 edge=-0.078
  - by vs_rth_vwap: above n=141 edge=-0.172; below n=55 edge=+0.140
  - by rvol_bucket: high n=34 edge=-0.203; low n=160 edge=-0.074
- **cvd_div_bearish MES 1h** edge by horizon: 60m: +0.040, 240m: +0.221
  - by session: ETH n=193 edge=+0.137; RTH n=34 edge=+0.694
  - by rvol_bucket: high n=38 edge=+0.417; low n=189 edge=+0.182
- **vwap_pullback_long NQ 5m** edge by horizon: 5m: -0.009, 15m: +0.018, 30m: -0.095, 60m: -0.323, 240m: -0.537
  - by session: ETH n=64 edge=-0.206; RTH n=30 edge=+0.143
- **vwap_pullback_long NQ 1h** edge by horizon: 60m: -0.002, 240m: +0.030
  - by session: ETH n=238 edge=-0.035; RTH n=110 edge=+0.169
  - by vs_rth_vwap: above n=248 edge=+0.050; below n=100 edge=-0.021
  - by rvol_bucket: high n=57 edge=+0.260; low n=291 edge=-0.016
- **vwap_pullback_long MNQ 5m** edge by horizon: 5m: +0.005, 15m: -0.046, 30m: -0.064, 60m: -0.323, 240m: -0.740
  - by session: ETH n=75 edge=-0.251; RTH n=31 edge=+0.390
- **vwap_pullback_long MNQ 1h** edge by horizon: 60m: +0.013, 240m: -0.001
  - by session: ETH n=233 edge=-0.047; RTH n=108 edge=+0.100
  - by vs_rth_vwap: above n=227 edge=+0.041; below n=114 edge=-0.084
  - by rvol_bucket: high n=57 edge=+0.218; low n=284 edge=-0.045
- **vwap_pullback_long ES 5m** edge by horizon: 5m: -0.045, 15m: -0.233, 30m: -0.156, 60m: -0.473, 240m: -1.478
- **vwap_pullback_long ES 1h** edge by horizon: 5m: +0.037, 15m: +0.054, 30m: +0.047, 60m: +0.033, 240m: +0.061
  - by session: ETH n=265 edge=-0.070; RTH n=127 edge=+0.334
  - by regime: balance n=31 edge=+0.410; trend n=361 edge=+0.031
  - by vs_rth_vwap: above n=274 edge=+0.122; below n=118 edge=-0.081
  - by rvol_bucket: high n=61 edge=+0.138; low n=331 edge=+0.046
- **vwap_pullback_long MES 5m** edge by horizon: 5m: -0.159, 15m: -0.298, 30m: -0.306, 60m: -0.503, 240m: -1.187
  - by session: ETH n=93 edge=-0.286; RTH n=31 edge=-0.368
  - by vs_rth_vwap: above n=91 edge=-0.328; below n=33 edge=-0.246
- **vwap_pullback_long MES 1h** edge by horizon: 60m: +0.008, 240m: +0.004
  - by session: ETH n=243 edge=-0.092; RTH n=121 edge=+0.196
  - by regime: balance n=30 edge=-0.179; trend n=334 edge=+0.020
  - by vs_rth_vwap: above n=251 edge=+0.097; below n=113 edge=-0.205
  - by rvol_bucket: high n=67 edge=-0.068; low n=297 edge=+0.020
- **vwap_pullback_short NQ 5m** edge by horizon: 5m: -0.048, 15m: -0.045, 30m: -0.155, 60m: -0.432, 240m: -0.333
  - by session: ETH n=66 edge=+0.010; RTH n=47 edge=-0.386
- **vwap_pullback_short NQ 1h** edge by horizon: 5m: +0.027, 15m: +0.035, 30m: +0.034, 60m: -0.008, 240m: +0.061
  - by session: ETH n=188 edge=-0.019; RTH n=82 edge=+0.246
  - by vs_rth_vwap: above n=100 edge=+0.059; below n=170 edge=+0.063
  - by rvol_bucket: high n=73 edge=-0.021; low n=197 edge=+0.092
- **vwap_pullback_short MNQ 5m** edge by horizon: 5m: -0.069, 15m: -0.055, 30m: -0.234, 60m: -0.489, 240m: -0.545
  - by session: ETH n=56 edge=-0.261; RTH n=41 edge=-0.197
- **vwap_pullback_short MNQ 1h** edge by horizon: 60m: -0.020, 240m: -0.027
  - by session: ETH n=181 edge=-0.047; RTH n=86 edge=+0.013
  - by vs_rth_vwap: above n=100 edge=-0.078; below n=167 edge=+0.003
  - by rvol_bucket: high n=81 edge=-0.194; low n=186 edge=+0.045
- **vwap_pullback_short ES 5m** edge by horizon: 5m: -0.068, 15m: +0.138, 30m: +0.225, 60m: +0.496, 240m: +0.901
  - by session: ETH n=59 edge=+0.218; RTH n=39 edge=+0.235
- **vwap_pullback_short ES 1h** edge by horizon: 5m: -0.025, 15m: -0.108, 30m: -0.065, 60m: -0.084, 240m: -0.030
  - by session: ETH n=189 edge=-0.006; RTH n=83 edge=-0.084
  - by vs_rth_vwap: above n=99 edge=-0.154; below n=173 edge=+0.042
  - by rvol_bucket: high n=67 edge=-0.107; low n=205 edge=-0.004
- **vwap_pullback_short MES 5m** edge by horizon: 5m: +0.006, 15m: +0.105, 30m: +0.164, 60m: +0.324, 240m: +0.792
  - by session: ETH n=56 edge=+0.056; RTH n=40 edge=+0.316
  - by vs_rth_vwap: above n=34 edge=+0.436; below n=62 edge=+0.016
- **vwap_pullback_short MES 1h** edge by horizon: 5m: +0.017, 15m: -0.047, 30m: +0.059, 60m: -0.099, 240m: -0.052
  - by session: ETH n=184 edge=+0.029; RTH n=80 edge=-0.240
  - by vs_rth_vwap: above n=104 edge=-0.106; below n=160 edge=-0.017
  - by rvol_bucket: high n=80 edge=-0.109; low n=184 edge=-0.027
- **rvol NQ 5m** edge by horizon: 5m: -0.014, 15m: -0.059, 30m: -0.002, 60m: -0.068, 240m: -0.236
  - by session: ETH n=320 edge=-0.015; RTH n=51 edge=+0.078
  - by vs_rth_vwap: above n=186 edge=-0.021; below n=185 edge=+0.017
  - by rvol_bucket: high n=337 edge=+0.008; low n=34 edge=-0.100
- **rvol NQ 1h** edge by horizon: 60m: +0.023, 240m: -0.028
  - by vs_rth_vwap: above n=134 edge=+0.075; below n=196 edge=-0.099
- **rvol MNQ 5m** edge by horizon: 5m: -0.091, 15m: -0.105, 30m: +0.011, 60m: +0.092, 240m: -0.021
  - by session: ETH n=274 edge=+0.030; RTH n=61 edge=-0.073
  - by vs_rth_vwap: above n=155 edge=+0.048; below n=180 edge=-0.021
  - by rvol_bucket: high n=300 edge=+0.008; low n=35 edge=+0.038
- **rvol MNQ 1h** edge by horizon: 60m: +0.046, 240m: +0.023
  - by vs_rth_vwap: above n=134 edge=+0.096; below n=180 edge=-0.031
- **rvol ES 5m** edge by horizon: 5m: -0.073, 15m: -0.091, 30m: -0.081, 60m: -0.043, 240m: -0.140
  - by session: ETH n=315 edge=-0.081; RTH n=66 edge=-0.078
  - by vs_rth_vwap: above n=126 edge=-0.105; below n=255 edge=-0.069
  - by rvol_bucket: high n=334 edge=-0.085; low n=47 edge=-0.051
- **rvol ES 1h** edge by horizon: 5m: -0.081, 15m: -0.032, 30m: -0.123, 60m: +0.004, 240m: -0.012
  - by vs_rth_vwap: above n=131 edge=+0.019; below n=217 edge=-0.031
- **rvol MES 5m** edge by horizon: 5m: -0.085, 15m: -0.070, 30m: -0.014, 60m: -0.024, 240m: -0.229
  - by session: ETH n=373 edge=-0.050; RTH n=86 edge=+0.144
  - by vs_rth_vwap: above n=156 edge=-0.205; below n=303 edge=+0.085
  - by rvol_bucket: high n=406 edge=-0.019; low n=53 edge=+0.028
- **rvol MES 1h** edge by horizon: 60m: -0.009, 240m: -0.016
  - by session: ETH n=343 edge=-0.012; RTH n=33 edge=-0.057
  - by vs_rth_vwap: above n=138 edge=-0.011; below n=238 edge=-0.019
