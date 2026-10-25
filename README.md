# Nasdaq-100 futures: Asian-session range breakout vs. mean reversion

A research project that discovers, implements, backtests and stress-tests systematic
strategies on **CME E-mini Nasdaq-100 futures (NQ)** built around the Asian-session range.
MNQ is covered as the lower-notional version.

> **Bottom line.** No candidate has a robust, validated edge after costs.
> * **Asian-range breakouts** lose money or just reflect market beta.
> * **A fade of failed breakouts** (mean reversion) was the strongest candidate in-sample:
>   final v3 TRAIN t = 1.80, VAL t = 1.81. It **failed the out-of-sample period**
>   (Jul 2024 – Oct 2026: −$81/trade, t = −0.48) and a rolling walk-forward (−$32/trade).
>   It is also weaker on an independent true-OHLC dataset.
>
> The Pine Script strategy is provided for **paper trading and further research only**.
> Nothing here is a promise of future profit. Nothing connects to a broker.

## Deliverables

| # | Deliverable | Location |
|---|---|---|
| 1 | Ranked research table of sources and strategies | [`docs/RESEARCH.md`](docs/RESEARCH.md) |
| 2 | What the evidence supports vs. what is speculative | [`docs/RESEARCH.md`](docs/RESEARCH.md#what-the-evidence-supports-and-what-is-speculative), [`docs/RESULTS.md`](docs/RESULTS.md#what-the-evidence-supports) |
| 3 | Breakout vs. mean-reversion comparison | [`docs/RESULTS.md`](docs/RESULTS.md#breakout-vs-mean-reversion-detailed-comparison) |
| 4 | Pine Script v6 strategy | [`pine/asian_range_strategy.pine`](pine/asian_range_strategy.pine), notes in [`docs/PINE.md`](docs/PINE.md) |
| 5 | Python backtester and configuration | [`asiabt/`](asiabt), [`config/strategies.json`](config/strategies.json), [`scripts/`](scripts) |
| 6 | Reproduction instructions | [below](#reproducing-everything) |
| 7 | Version-by-version improvement log | [`docs/IMPROVEMENT_LOG.md`](docs/IMPROVEMENT_LOG.md) |
| 8 | Performance tables: baselines, validation, OOS, walk-forward, robustness | [`docs/RESULTS.md`](docs/RESULTS.md), [`docs/RESULTS_TABLES.md`](docs/RESULTS_TABLES.md) |
| 9 | Code-quality and evidence-quality scores | [below](#scores) |
| 10 | Known weaknesses, data subscriptions, next steps | [below](#known-weaknesses) |
| – | Data sources, validation, sessions, execution model | [`docs/DATA.md`](docs/DATA.md) |
| – | Quantitative integrity audit: defects, fixes, before/after, parity status, data plan | [`docs/AUDIT.md`](docs/AUDIT.md) |
| – | Pre-registered protocol for the independent pre-2020 test and future research | [`docs/PREREGISTRATION.md`](docs/PREREGISTRATION.md) |

## Final candidate (v3), in one paragraph

Build the high and low of 18:00–00:00 New York time (the CME Globex trading day starts at
18:00). Between 00:00 and 08:00, track how far price has gone beyond the range on completed
5-minute bars. If the excursion beyond one side is between **0.10 and 0.225 × ATR14** (daily,
prior days only) and a 5-minute bar then **closes back inside the range**, enter against the
excursion at the next bar's open. The stop sits just beyond the excursion extreme (+0.05 × ATR)
and the target is the opposite side of the range. Flatten at 11:00. At most 2 trades per
session, long and short.

| NQ, 1 contract, base costs | TRAIN 2020-01 → 2022-12 | VAL 2023-01 → 2024-06 | **OOS 2024-07 → 2026-10 (previously inspected)** |
|---|---|---|---|
| Trades | 206 | 101 | 161 |
| Net profit | $39,896 | $16,838 | **−$13,090** |
| Profit factor | 1.34 | 1.49 | **0.92** |
| Win rate | 54.9% | 64.4% | 46.0% |
| Avg trade (t-stat) | $194 (1.80) | $167 (1.81) | **−$81 (−0.48)** |
| Sharpe (daily, annualised) | 1.08 | 1.48 | −0.32 |
| Max drawdown | −$16,763 | −$5,210 | −$33,630 |

## Repository layout

```
asiabt/            Python package: data loading + session grid, engine, metrics, research helpers
scripts/           fetch_tos_kaggle.py, fetch_crosscheck.py, validate_data.py, stats_asia.py,
                   sweep_candidates.py, select_v1.py, evaluate.py, cycles.py, walk_forward.py,
                   robustness.py, make_report.py, lint_pine_tradingview.js
config/            strategies.json: frozen baselines, candidates and versions (append-only)
pine/              asian_range_strategy.pine (Pine Script v6 strategy)
docs/              RESEARCH, DATA, RESULTS, RESULTS_TABLES (generated), IMPROVEMENT_LOG, PINE
results/           every generated CSV/JSON (sweeps, evaluations, trade lists, walk-forward, robustness)
tests/             pytest suite: session mapping, fills, stop-first, gaps, trade-through, look-ahead
data/              downloaded/derived data (git-ignored; rebuilt by the fetch scripts)
```

## Reproducing everything

Requires Python ≥ 3.10 and roughly 2 GB of free disk. No API keys are needed: all data is
public and downloaded anonymously.

```bash
pip install -e ".[test]"
python -m pytest -q                                   # 34 unit/property tests

# 1. Data (≈0.8 GB zip from Kaggle, then reduced to 1-minute bars)
python scripts/fetch_tos_kaggle.py                    # -> data/nq_tos_1m.parquet  (primary, /NQ)
python scripts/fetch_tos_kaggle.py --col /ES --out data/es_tos_1m.parquet   # out-of-market check
python scripts/fetch_crosscheck.py                    # Yahoo NQ=F 1h + independent NQ 1m (Kaggle CC0)
python scripts/validate_data.py                       # -> results/data_validation.json

# 2. Research pipeline (TRAIN/VAL only until evaluate.py)
python scripts/stats_asia.py                          # descriptive Asian-range statistics
python scripts/sweep_candidates.py A B B2             # ~11 min on 4 cores
python scripts/select_v1.py                           # pooled TRAIN+VAL selection of A rep., B v1, C threshold
python scripts/cycles.py                              # the four improvement cycles
python scripts/evaluate.py                            # all frozen strategies incl. OOS -> results/eval/
python scripts/walk_forward.py                        # rolling 24m/6m walk-forward
python scripts/robustness.py                          # independent data, /ES, session defs, bootstrap
python scripts/make_report.py                         # -> docs/RESULTS_TABLES.md

# 2b. Integrity audit (docs/AUDIT.md §8 lists every command)
python scripts/integrity_metrics.py && python scripts/integrity_ambiguity.py && python scripts/integrity_data_exec.py
python scripts/integrity_before_after.py && python scripts/deflated_sharpe.py && python scripts/parity_resolution.py

# 3. Pine static check (optional; needs Node + Playwright with Chromium)
NODE_PATH=$(npm root -g) node scripts/lint_pine_tradingview.js pine/asian_range_strategy.pine
```

The Kaggle dataset `brtnsmth/intraday-market-data` is updated weekly, so a fresh download
contains newer weeks. The splits are fixed by date in `asiabt/research.py`, so TRAIN/VAL/OOS
numbers reproduce, while "full sample" numbers grow as data is added.

## Scores

Scores were revised after the **quantitative integrity audit** ([`docs/AUDIT.md`](docs/AUDIT.md), 2026-10-25).
The scores from before the audit (code 8.5, evidence 7.5) are kept in the git history at `50f822f`.

* **Code quality: 9.0 / 10.** 34 tests. Two defects were found and fixed with reproducing tests:
  * a drawdown baseline error (1 of 52 values changed);
  * a two-sided fade short bias (never triggered for v1/v2/v3).

  Frozen results reproduce bit-for-bit. **Pine compile, Strategy Tester run and Python/Pine
  trade parity remain unverified** (they need a TradingView login). The static analysis passes,
  and the parity tooling is built and tested.
* **Evidence quality: 7.0 / 10** (down from 7.5).
  * The 2024-07+ OOS period was previously inspected, so it is not a holdout.
  * Snapshot-built bars change which trades occur.
  * Every day-block bootstrap CI of mean daily P&L includes 0.
  * The Deflated Sharpe Ratio of v3's in-sample Sharpe is below 0.95 once more than ~5
    independent trials are assumed. About 7,000 configurations were explored.
  * A genuinely independent pre-2020 test is pre-registered ([`docs/PREREGISTRATION.md`](docs/PREREGISTRATION.md)),
    but it hasn't been run because the data purchase needs approval.

Item-by-item scoring: `docs/AUDIT.md` §9.

## Known weaknesses

* **No validated edge.** The final candidate's OOS and walk-forward results are ≤ 0. Every
  in-sample improvement made OOS worse than v1, which is a sign of over-fitting the validation period.
* **Multiple testing.** About 7,000 configurations were evaluated. A Deflated Sharpe Ratio was
  added in the audit: for v3 it is 0.92 at 10 assumed independent trials, 0.57 at 1,000 and
  0.42 at 7,000. White's Reality Check / SPA was not run because per-trial return series weren't
  stored. No adjustment removes selection bias completely.
* **Data.** Snapshot-derived minute bars, a single recorder (with gaps such as March 2020), and
  2020+ only. Volume-confirmed breakouts couldn't be tested on the primary data.
* **Data-source sensitivity.** On true exchange OHLC data (2023–2025), v3 earns $69 instead of
  $166 per trade on the same days.
* **Execution model.** 1-minute resolution and a fixed 1-tick slippage. Queue position, the
  thinner overnight book in fast markets, and exchange price limits aren't modelled.
* **Pine.** Not compiled or run in TradingView (needs a login). Python–Pine parity is unverified.
* **Benchmarks.** A passive long 00:00→04:00 ET benchmark beat every developed candidate on
  OOS Sharpe (0.51), and it isn't significant either.

## Required data subscriptions (for a stronger study)

* **Databento** `GLBX.MDP3` NQ/MNQ (OHLCV-1m, or trades/MBP-1 for exact fills), 2010 onward:
  true exchange extremes, volume, explicit contract rolls. Pay-as-you-go.
* Alternatives: **FirstRate Data** NQ 1-minute (2008+, about $100/year updates), **CME DataMine**,
  **Interactive Brokers** historical API (needs an account), **TradingView** Premium for Bar
  Magnifier and deeper intraday history (needed to run the Pine strategy over the full sample).

## Next steps

1. Re-run the **frozen v1 and v3 rules, unchanged**, on 2010–2019 Databento NQ data. That's a
   genuinely new out-of-sample test, and the cheapest way to settle whether the in-sample fade
   effect is real.
2. Paper trade v1/v3 forward on **MNQ** (TradingView paper or broker simulator) for at least
   6 months. Pre-register the evaluation: mean trade > 0 with t > 2 over ≥ 150 trades.
3. Run the Pine strategy in the Strategy Tester (with Bar Magnifier) and reconcile its trade
   list with `results/eval/trades_B_fade_v3.csv`.
4. Test volume/order-flow confirmation of breakouts once volume data is available. Apply a
   deflated-Sharpe correction to any new search.
