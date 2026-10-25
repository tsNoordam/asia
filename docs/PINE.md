# Pine Script v6 strategy: `pine/asian_range_strategy.pine`

## Verification status (updated by the integrity audit, 2026-10-25)

| Check | Status |
|---|---|
| TradingView in-editor static analysis | **Passed: 0 errors, 0 warnings over all 328 lines** after the audit changes (`scripts/lint_pine_tradingview.js`; a planted undeclared identifier at the end is flagged, so the whole file was analysed). **This is not a compile.** |
| Full compile ("Add to chart") | **NOT VERIFIED.** It needs a TradingView login, which this environment doesn't have |
| Strategy Tester run | **NOT VERIFIED** (same reason) |
| Python ↔ Pine trade-level parity | **NOT VERIFIED.** No TradingView trade list exists yet. The comparison tooling is built and unit-tested (see the protocol below) |
| Resolution component of parity (measured in Python) | Done: on 5-minute bars (a 5-min chart) all 472 v3 signals are identical to 1-minute execution. 13 exit reasons differ, costing −$4.4k in total (−$9/trade), mostly in VAL (`results/parity/resolution.json`) |

## Parity protocol (to be run by a human with a TradingView account)

1. **Same inputs.** Chart `CME_MINI:NQ1!`, **1-minute**, timezone *America/New_York*, continuous
   contract **unadjusted** (turn B-ADJ off) to match the unadjusted TOS data. Default inputs
   (= `B_fade_v3r1`). Properties: commission $2.50/side, slippage 1 tick, limit-fill threshold
   1 tick, Bar Magnifier off for the first run (and on for a second run).
2. **Date range.** A window where TradingView has 1-minute history and the Python data overlaps,
   e.g. the most recent 2–3 months up to 2026-10-23.
3. **Export.** Strategy Tester → *List of trades* → Export (CSV).
4. **Python side.** `python scripts/evaluate.py B_fade_v3r1` writes `results/eval/trades_B_fade_v3r1.csv`.
5. **Compare.**
   `python scripts/parity_compare.py --tv <export.csv> --py results/eval/trades_B_fade_v3r1.csv --start <first day> --end <last day>`
   This writes `results/parity/report.json` with matched, unmatched and classified pairs.
6. **Classify and resolve.**
   * `adjustment`: the chart was back-adjusted. Redo the run unadjusted.
   * `resolution` / `intrabar_exit`: expected from TradingView's intrabar path assumption. Quantify it; it isn't a defect.
   * `price_diff` or unmatched trades: check the bar data first (snapshot vs exchange OHLC, see
     AUDIT.md §3), then the code. Any remaining logic mismatch is an **implementation defect** and gets a test.
7. **Record the outcome** in this file: matched %, P&L difference, and a list of defects found.
   Only then can parity be marked as verified.

## How to use

1. Open a CME `NQ1!` or `MNQ1!` chart. Use a **1-minute chart** for the closest match to the
   Python backtest (5-minute signal bars, 1-minute fills). A 5-minute chart with
   *Signal bar length* = 5 also works but resolves stops and targets more coarsely.
2. Check **Settings → Properties**: commission (default $2.50 per contract per side for NQ, so
   $5 round turn; use ≈ $0.65 for MNQ), slippage (default 1 tick), and the limit-fill threshold
   (`backtest_fill_limits_assumption` = 1 tick). Bar Magnifier (premium) improves intrabar fills.
3. On the 1-minute chart, TradingView's history depth limits how many sessions are tested,
   depending on your plan.

## Inputs

| Group | Input | Default | Meaning |
|---|---|---|---|
| Sessions | Session timezone | America/New_York | IANA timezone for every time input. DST is handled automatically |
| | Trading-day start | 18:00 | CME Globex day start. Used to compute minute offsets |
| | Asian range start / end | 18:00 / 00:00 | The range is built from bars that open inside [start, end) |
| | Last entry | 08:00 | A signal bar must close at or before this time |
| | Flatten at | 11:00 | Market exit, filled at the open of this minute |
| | Signal bar length | 5 | Minutes. Signal bars are aggregated from chart bars and aligned to the range end |
| Mode and risk | Strategy mode | Fade | Fade / Breakout / Hybrid (breakout if range/ATR < threshold) |
| | Direction | Both | Both / Long only / Short only |
| | Max trades per session | 2 | Counts entries per trading day |
| | Hybrid threshold | 0.207 | Range/ATR tercile edge from TRAIN |
| Fade | Min / max excursion | 0.10 / 0.225 | Furthest point beyond the range (since range end or the last trade), in ATR or range-width units |
| | Stop buffer | 0.05 × ATR | Beyond the excursion extreme |
| | Target | Opposite boundary | Or Midpoint, or an R multiple |
| Breakout | Close beyond range by | 0 × ATR | Confirmation buffer |
| | Stop | ATR, 0.5 | Or opposite boundary / midpoint |
| | Target R | 1.5 | 0 = time exit only |
| Day filters | Min / max range/ATR | 0 / 99 | Skip days outside this band |
| | Trend filter | None | Prior daily close vs daily SMA20 (both lagged one day) |
| | Min share of range bars | 0.9 | Data-coverage safeguard (holidays, outages) |

Default values = **v3**. For v1, set max excursion = 99 and max trades = 1.

## Long and short rules (Fade mode)

* **Short.** After the range closes, track the highest signal-bar high. If it is above the
  range high by at least *min* and at most *max* excursion, and a signal bar then **closes back
  inside** the range, sell at the next bar's open. Stop = highest high + buffer. Target = range low.
* **Long.** The mirror image, below the range low. Target = range high.
* **Both modes.** Flat at the deadline, at most *max trades* per session, no new entry while a
  position is open, no position carried into the next session.

## Repainting and look-ahead safeguards

* The range is final only once the first bar at or after the range end has opened.
* Signals use only completed signal bars. `calc_on_every_tick = false` and
  `process_orders_on_close = false`, so entries fill at the next bar's open.
* Daily ATR, SMA20 and the previous close come from
  `request.security(..., expr[1], lookahead = barmerge.lookahead_on)`, the documented
  non-repainting idiom for completed higher-timeframe values.

## Safeguards against duplicate or unintended positions

`pyramiding = 0`. Entries are allowed only when `strategy.position_size == 0`, with a per-session
trade counter. Brackets are tied to their own entry ID. `strategy.close_all` runs at the
deadline and at any new session, and `strategy.cancel_all` runs only when flat, so it can never
cancel the exit order. Inputs are validated with `runtime.error`.

## Alerts

`alert()` fires once per bar close on each entry signal (side, stop, target) and on the time
exit. Order-fill alerts can also be created from the Strategy's alert dialog.

## Known differences from the Python engine

| Topic | Python (`asiabt`) | Pine |
|---|---|---|
| Intrabar ordering | Stop assumed first when a 1-min bar touches both stop and target | TradingView's broker emulator infers the path from the bar's OHLC. Use a 1-min chart or Bar Magnifier |
| Rejected orders | Skip the trade if the next open is already beyond the stop or target | Checks against the signal close instead, since the next open is unknown. A gap-through exits immediately |
| R-multiple targets | Computed from the actual fill | Placed provisionally from the signal close, then re-anchored on `strategy.position_avg_price` from the next bar |
| ATR | SMA(14) of true range on a back-adjusted daily series | `ta.sma(ta.tr(true), 14)` on TradingView daily bars. Results depend on the continuous-contract adjustment setting (B-ADJ) |
| Data | 3-second snapshot bars (TOS) | Exchange data. The independent-data check in RESULTS shows the fade's results **fall** on true OHLC bars |
| Volume / options | Not used | Not used. No IV or options data, and no proxy for one |
| Two-sided ambiguous fade signal | `fd_both_sides`: `latest` in r1 configs (fade the side with the more recent extreme, 1-min resolution; same minute → skip). Frozen v1/v3 use `legacy_short_first` | Input *If both sides qualify*, default *Latest extreme*, timed at chart-bar resolution (on a 5-min chart more cases become "same bar" → skipped). Never triggered on 2020–2026 data for v1/v2/v3 |
| Signal bar after an exit | Skips the signal bar that contains the exit minute | Same since the audit (`exitedNow`) |
