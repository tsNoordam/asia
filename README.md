# Nasdaq-100 futures: Asian-session range breakout vs. mean reversion

A research project that discovers, implements, backtests and stress-tests systematic
strategies on **CME E-mini Nasdaq-100 futures (NQ)** built around the Asian-session range.
MNQ is covered as the lower-notional version.

> **Bottom line.** No candidate has a robust, validated edge after costs.
> * **Asian-range breakouts** lose money or just reflect market beta.
> * **A fade of failed breakouts** (mean reversion) was the strongest candidate in-sample:
>   final v3 TRAIN t = 1.80, VAL t = 1.81. It **failed the untouched out-of-sample period**
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

## Final candidate (v3), in one paragraph

Build the high and low of 18:00–00:00 New York time (the CME Globex trading day starts at
18:00). Between 00:00 and 08:00, track how far price has gone beyond the range on completed
5-minute bars. If the excursion beyond one side is between **0.10 and 0.225 × ATR14** (daily,
prior days only) and a 5-minute bar then **closes back inside the range**, enter against the
excursion at the next bar's open. The stop sits just beyond the excursion extreme (+0.05 × ATR)
and the target is the opposite side of the range. Flatten at 11:00. At most 2 trades per
session, long and short.

| NQ, 1 contract, base costs | TRAIN 2020-01 → 2022-12 | VAL 2023-01 → 2024-06 | **OOS 2024-07 → 2026-10** |
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
python -m pytest -q                                   # 13 unit/property tests

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

# 3. Pine static check (optional; needs Node + Playwright with Chromium)
NODE_PATH=$(npm root -g) node scripts/lint_pine_tradingview.js pine/asian_range_strategy.pine
```

The Kaggle dataset `brtnsmth/intraday-market-data` is updated weekly, so a fresh download
contains newer weeks. The splits are fixed by date in `asiabt/research.py`, so TRAIN/VAL/OOS
numbers reproduce, while "full sample" numbers grow as data is added.

## Scores

Scored with the rubric from the brief. Each point is backed by evidence that was actually
produced. Anything unverified is marked.

### Code quality: **8.5 / 10**

| Item | Score | Reason |
|---|---|---|
| Correctness and compilability | 1.5 / 2 | Python: 13 passing tests, deterministic, reproduces every reported number from scripts. Pine: **passes TradingView's in-editor static analyser with 0 errors / 0 warnings** (verified headlessly, with a positive control). A full compile ("Add to chart") and a Strategy Tester run **were not possible without a TradingView login and are unverified** |
| Execution and risk-management logic | 1.5 / 2 | Next-bar-open fills, stop-first intrabar rule, gap-through stops, limit trade-through, order rejection, time stop, per-session trade cap, costs/slippage, MNQ economics. Pine mirrors this with documented differences (intrabar path, rejection proxy) that haven't been reconciled numerically |
| Repainting and look-ahead safeguards | 2 / 2 | The range is final only after its window closes. Signals use completed bars only. Daily features are lagged one day and roll back-adjustment can't leak the future. Property tests perturb all future bars and check that earlier trades and features don't change. Pine uses the documented `expr[1]` + `lookahead_on` idiom and `calc_on_every_tick = false` |
| Readability and configurability | 2 / 2 | Small package, one `Params` dataclass, frozen JSON configs, every Pine input documented with tooltips |
| Diagnostics, testing and documentation | 1.5 / 2 | Data-validation report, trade lists, exit reasons, MAE/MFE, a Pine diagnostics table and alerts, full docs. Missing: a Pine-vs-Python trade-by-trade parity test |

### Evidence quality: **7.5 / 10** (below the 8/10 target)

| Item | Score | Reason |
|---|---|---|
| Data quality and realistic costs | 1.5 / 2 | Real NQ front-month data, 2020–2026 (1,667 sessions), validated against two independent sources: timezone/DST confirmed, closes match within 1 pt 82% of the time. Costs are realistic and stress-tested. **But** the bars are built from 3-second snapshots (highs and lows understated by a median 0.25 pt), there is no /NQ volume, and the final strategy's result **halves** on the independent true-OHLC data |
| Out-of-sample and walk-forward | 1.5 / 2 | Chronological TRAIN/VAL/OOS fixed before tuning, plus a 10-window rolling walk-forward. OOS never drove a decision, but it was *viewed* after each of the 4 cycles, so it's no longer pristine for future work |
| Robustness across parameter changes | 1 / 2 | Sensitivity was measured thoroughly: one-at-a-time, neighbour rules, sessions, costs, /ES. It shows the in-sample plateau **doesn't carry over to OOS**, so the evidence for robustness is weak |
| Sample size and regimes | 1.5 / 2 | Covers the 2020 crash, the 2021 bull market, the 2022 bear market, the 2025 tariff shock and 2026. The final strategy has only ~470 trades in total and 161 OOS, with no pre-2020 history |
| Transparent and reproducible reporting | 2 / 2 | Public data, scripts for every step, append-only configs, all failed and rejected variants reported, OOS degradation stated plainly |

A high code score says nothing about profitability. The evidence quality is good enough to
support a **negative** conclusion: no validated edge.

## Known weaknesses

* **No validated edge.** The final candidate's OOS and walk-forward results are ≤ 0. Every
  in-sample improvement made OOS worse than v1, which is a sign of over-fitting the validation period.
* **Multiple testing.** About 7,000 configurations were evaluated. No deflated-Sharpe or
  White's Reality Check correction was applied; the OOS and walk-forward results serve as the
  practical check.
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
