# Data, sessions and execution assumptions

## Data sources

| Role | Source | Instrument | Timeframe | Period | Notes |
|---|---|---|---|---|---|
| **Primary** | Kaggle [`brtnsmth/intraday-market-data`](https://www.kaggle.com/datasets/brtnsmth/intraday-market-data) (ThinkOrSwim recorder, CC0) | **/NQ front month** (CME E-mini Nasdaq-100) | ~3-second last-price snapshots → 1-minute OHLC | 2020-01-26 → 2026-10-23 (1,667 trading days) | Unadjusted front month. Timestamps America/New_York. No /NQ volume |
| Cross-check 1 | Kaggle [`tgtanalytics/nq-futures-1min-bar-2022-2025`](https://www.kaggle.com/datasets/tgtanalytics/nq-futures-1min-bar-2022-2025) (CC0) | NQ continuous, **back-adjusted** | 1-minute OHLCV, labelled at bar **end**, ET | 2022-12-26 → 2025-12-11 | File stops at Excel's 1,048,575-row limit |
| Cross-check 2 | Yahoo Finance `NQ=F` via `yfinance` | NQ front month | 1 hour | 2024-06 → 2026-10 | ~730-day limit on hourly data |
| Rejected | Dukascopy `USATECHIDXUSD` | Nasdaq-100 **CFD** | 1 minute | 2012+ | Not used. Persistent HTTP 429/503 throttling made a 14-year download impractical, and it's a CFD, not NQ |
| Rejected | Hugging Face `lynx1231/...-sample` | NQ individual contracts | 1 minute | ~2025–2026 | Evaluation sample only |

Databento, IB, FirstRate Data and TradingView exports were considered. All need a paid
subscription or a credential this environment doesn't have.

**QQQ, the NDX cash index, CFDs, NQ and MNQ are not treated as interchangeable.** Every
result here is on NQ futures prices. MNQ prices are identical, but the multiplier is
$2/pt instead of $20/pt and commissions are a much larger share of each trade (see
`docs/RESULTS.md`, MNQ section).

## Validation (`python scripts/validate_data.py` → `results/data_validation.json`)

* **Timezone / DST.** Minute closes were matched against cross-check 1 after removing its
  back-adjustment (a constant offset per contract). 81.7% of minute closes agree within 1
  point: 81.8% in EDT months and 81.6% in EST months. Shifting either series by ±60 minutes
  drops agreement to 4.7%, so the TOS timestamps are New York wall-clock in both DST regimes.
* **Sampling error.** Snapshot-built highs understate the true 1-minute high by a median
  0.25 pt (p90 1.5 pt, p99 4.5 pt). Lows are the same. Both stops and targets are slightly
  under-triggered, roughly symmetrically. Asian-range highs/lows differ by a median of
  0.5–0.75 pt from the true values.
* **Hourly cross-check vs Yahoo `NQ=F`.** Median |close difference| 0.75 pt, and 79.9% of
  hours agree within 2 points.
* **Stale prices.** The recorder keeps writing the last price while CME is closed (17:00–18:00
  halt, holidays, early closes). Runs of ≥ 10 consecutive minutes with no price change are
  removed (2.42 M → 2.26 M minutes). The data stays continuous across real trading.
* **Coverage.** 35 trading days have < 80% of minutes, mostly holidays and recorder outages
  such as March 2020. Strategies skip any day where < 90% of the Asian-range minutes or
  < 80% of the trading-window minutes are present.
* **Rolls.** /NQ is unadjusted. 24 roll days show a gap at the 18:00 open equal to the
  calendar spread. A scan of every intraday 1-minute jump > 0.15 × ATR found **no
  mid-session contract switches**: the large jumps are 08:30 ET data releases or recorder gaps.
  Intraday P&L is therefore unaffected. Daily features (ATR14, SMA20/50, 5-day return) are
  computed on a back-adjusted daily series, and the roll gap is excluded from true range.

## Sessions (America/New_York)

A CME Globex trading day *D* runs 18:00 (*D*−1) → 17:00 (*D*). It's stored as 1,380
one-minute slots, offset 0 = 18:00. Because every window is defined in NY wall-clock time,
DST transitions need no special handling. A unit test checks the 2024-03-10 spring-forward
session.

| Concept | Definition used |
|---|---|
| Asian-range construction (hypotheses compared) | R1 18:00–00:00, R2 18:00–02:00, R3 20:00–02:00 (the TradingStats / NQ Stats definition) |
| Range availability | After the last 1-minute bar *inside* the window closes, i.e. at `range_end`. The first signal bar closes at `range_end + tf` |
| European breakout window | `range_end` → `entry_cutoff` (05:00 / 08:00 / 11:00 tested) |
| NY regular trading hours | 09:30–16:00 (used only for the RTH close feature and the flat-time choice) |
| Flatten deadline | `flat_time`, 11:00 or 16:00. Market exit at the open of that minute |
| Trading-day boundary | 17:00 halt. Nothing is carried across it |

## Execution and cost model (`asiabt/engine.py`)

* Signals are evaluated only on completed `tf`-minute bars (5 or 15). Entry is a market order
  at the **next** 1-minute bar's open, plus 1 tick of adverse slippage. The signal bar's close
  is never used as the fill.
* Stops are stop-market orders: fill at the stop − 1 tick, or at the bar's open − 1 tick if
  the bar gaps through.
* Targets are limit orders: fill at the limit only if price trades **through** it by 1 tick.
* If one 1-minute bar touches both the stop and the target, the stop fills first.
* Orders are rejected (no trade) when the next-open fill would already be beyond the stop or target.
* NQ: tick 0.25 pt = $5. $20/pt. Commission + fees **$5.00 per round turn**. Slippage 1 tick
  per side on market/stop fills. Typical round trip ≈ 0.5 pt slippage + 0.25 pt commission
  ≈ $15. Cost stress tests use 2 ticks per side and $7 commission.
* One contract, no compounding, no position overlap, at most `max_trades` per session.
* Not modelled: queue position beyond the 1-tick trade-through rule, exchange outages,
  margin changes, and CME dynamic/overnight price limits.
