# Pre-registered research protocol

Written on 2026-10-25, **before** any pre-2020 data was acquired or looked at. Changes to this
file after data acquisition must be committed separately and justified. They may never be
motivated by the new data's results.

## 1. Frozen rules under test

From `config/strategies.json`, unchanged:

| Role | Config | Notes |
|---|---|---|
| Primary hypothesis | `B_fade_v3r1` | v3 rules with the chronological two-sided rule (`fd_both_sides = latest`). On 2020–2026 data its trades are identical to frozen `B_fade_v3` |
| Secondary hypothesis | `B_fade_v1r1` | v1 rules, same semantics |
| Reported, not tested | `B_fade_v3`, `B_fade_v1` (legacy semantics), `B1_simple_breakout`, `B2_simple_fade`, `B4_eu_open_long_00_04`, `A_breakout_both` | Context only |

No parameter, filter, session definition or cost assumption may change for this test.

## 2. Independent sample

* **Data.** CME NQ outright futures, 1-minute OHLCV built from exchange trades: Databento
  `GLBX.MDP3`, schema `ohlcv-1m`, parent symbol `NQ.FUT`, plus the `definition` schema.
  Fetched with `scripts/fetch_databento_nq.py` only after the user approves the cost quote.
* **Period.** 2010-06-06 (dataset start) → 2019-12-31. No overlap with the 2020+ research data
  is permitted, and `scripts/evaluate_independent.py` refuses later data.
* **Conversion** (`asiabt/independent.py`, unit-tested before acquisition):
  * outright contracts only;
  * front month = most active contract on the **previous** trading day;
  * quiet-minute gaps of ≤ 30 minutes inside a session are filled flat at the previous close;
    longer gaps stay missing;
  * NY wall-clock time;
  * prices unadjusted;
  * no stale-snapshot filter, because these bars come from exchange trades.
* **Costs.** Base: $5 round turn + 1 tick of slippage per side, with limit fills requiring
  1 tick of trade-through. Stress: $7 + 2 ticks. Fixed dollar costs are applied even though NQ
  prices (and therefore point ranges) were 3–10× lower in 2010–2019. This is conservative, and
  it is the realistic cost structure.

## 3. Decision rule (`verdict()` in `scripts/evaluate_independent.py`)

A hypothesis is **supported** only if all of the following hold on 2010-06 → 2019-12 at base costs:

1. **Primary.** Newey–West t of mean daily P&L > **2.24**, which is a one-sided α = 0.0125
   Bonferroni bound for the 2 hypotheses tested. Also, the lower bound of the day-block bootstrap
   95% CI of mean daily P&L must be > 0.
2. Mean daily P&L > 0 under **stressed** costs.
3. Net P&L > 0 in at least 60% of calendar years.
4. Mean trade > 0 for **both** long and short trades.

If the primary hypothesis is not supported, the fade hypothesis is **rejected** for this rule
family. There is no re-tuning on 2010–2019 data. A rescue attempt would need yet another unseen
period (e.g. forward paper trading) and a new pre-registration.

## 4. Rules for any future research (Stage 7)

* **Hypotheses first.** At most 3 explicit hypotheses per study, each stating its mechanism
  (e.g. the stop/take-profit clustering behind failed breakouts) and the direction of the effect.
* **Frozen baselines.** Every study reports B0–B5 and the frozen v1/v3 alongside new candidates.
* **Limited search space.** The full grid is written down before running (≤ 200 configurations
  per hypothesis). The total count of configurations ever evaluated is logged in
  `docs/IMPROVEMENT_LOG.md`. Currently ≈ 7,000 + 2,592 (the DSR variance sweep, which was
  measurement only).
* **Chronology.** TRAIN → VALIDATION for any choice. Walk-forward where feasible. A test period
  that nobody has looked at and that is opened **once**. The 2024-07 → 2026-10 period is
  previously inspected and may only be used as a descriptive check, never for selection.
* **Reporting.** Base and stressed costs; sensitivity of one step around each chosen
  parameter; long/short separately; year by year; daily equity curve and drawdown from a 0
  baseline; trade-level and daily-level (Newey–West, day-block bootstrap) inference.
* **Multiple testing.** Report a Deflated Sharpe Ratio across a range of assumed independent
  trial counts (`scripts/deflated_sharpe.py`). Where trial return series are kept, also run a
  White Reality Check / Hansen SPA-style bootstrap. No single adjustment removes selection bias
  entirely, and none corrects for decisions made while *designing* a grid.
* **Data constraints.** No volume or order-flow features while the primary dataset lacks
  reliable volume (the TOS /NQ series has none). Every feature needs a hypothesis stated
  before testing and must not be selected on the final holdout.
* **Parity.** Before any paper trading, a TradingView Strategy Tester trade list must be
  reconciled with the Python trade list using `scripts/parity_compare.py`, and the differences
  classified.
