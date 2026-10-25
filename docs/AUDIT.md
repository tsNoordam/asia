# Quantitative integrity audit (2026-10-25)

**Scope.** Does the research infrastructure produce statistically and operationally trustworthy
conclusions about `B_fade_v3`? No new strategy and no parameter search was done. The one sweep
re-scored here (for the Deflated Sharpe variance) is measurement only.

**Bottom line.**
* The infrastructure had **two real but low-impact defects**:
  * the drawdown baseline, which changed 1 of 52 reported values;
  * a short bias in the fade engine when both sides qualify, which never triggered for v1/v2/v3.
* There was also one process defect, and wording that overstated the OOS period.
* After the fixes, the conclusion is unchanged and somewhat stronger:
  * there is **no statistically defensible edge**;
  * the in-sample Sharpe of v3 is not significant after allowing for the search (Deflated
    Sharpe 0.57 at 1,000 assumed independent trials, 0.42 at 7,000);
  * the in-sample result depends materially on the data source.

## 0. Baseline (Stage 0)

| Item | Value |
|---|---|
| Branch / HEAD before the audit | `claude/awesome-turing-flccrd` @ `50f822f` (identical to origin, clean tree) |
| Before-state snapshot | `results/baseline_50f822f/`: eval reports and trade lists, walk-forward, robustness, cycles, data validation, plus `SHA256SUMS` of the data files, config, `asiabt/*.py` and the Pine script |
| Local data present | `data/nq_tos_1m.parquet` (sha256 `99a4f74e…`), `data/es_tos_1m.parquet`, `data/raw/tos_dataset.zip`, `data/raw/crosscheck/*` (git-ignored, not on GitHub) |
| Tests before | 13 passed |
| Baseline reproduction | v1 and v3 TRAIN/VAL trades, net, t and drawdown reproduced exactly. After the engine change, all 13 frozen strategies' trade lists are **bit-identical** to the snapshot (legacy semantics) |

Branching: work stayed on the designated branch, as required by this session. The before-state
is commit `50f822f` plus the snapshot directory; no history was rewritten.

## 1. Verified defects

| ID | Severity | Location (at 50f822f) | Defect | Reproducing test | Fix | Effect on reported results |
|---|---|---|---|---|---|---|
| D1 | Medium (metric) | `asiabt/metrics.py:31-32` | The drawdown running peak started at the first day's equity, not at 0, so losses before the first new high were ignored. A period starting −500, −300 reported **$0** drawdown | `tests/test_metrics.py::test_negative_first_day_counts_as_drawdown` and 6 related cases | `max_drawdown()` adds the 0 starting equity (`asiabt/metrics.py:41`) | 1 of 52 strategy-period values: B4 EU-open OOS −$19,725 → **−$19,920**. No candidate number changed (`results/integrity/metric_corrections.csv`, `before_after.csv`) |
| D2 | Medium (logic), zero realised impact | `asiabt/engine.py:268-271`, `pine/asian_range_strategy.pine:217-222` | If the upper and lower excursions both qualified at one signal close, `if up … elif down` always chose the **short** | `tests/test_engine.py::test_both_sides_same_minute_legacy_reproduces_short_bias` | New `fd_both_sides` rule (`engine.py:76`, `282-289`): fade the side whose extreme was set most recently at 1-minute resolution; if both were set in the same minute, skip. Pine input *If both sides qualify* (`pine:73`, `237-246`). Frozen configs keep `legacy_short_first` so they reproduce. Corrected configs are `B_fade_v1r1`, `B_fade_v3r1` | 0 ambiguous trades for v1, v2, v3, C (all periods). 1 of 1,387 trades in baseline B2, worth +$295 under the corrected rule (`results/integrity/ambiguity.csv`) |
| D3 | Process | `scripts/evaluate.py` `--no-oos` | A development run overwrote the frozen full report (happened once in the previous session and was repaired in commit `50f822f`) | — | `--no-oos` now writes to `results/eval_dev/` (`evaluate.py:114`) | None now |
| D4 | Latent | `asiabt/metrics.py:30` | `reindex(days)` silently dropped trades outside the evaluation days from the daily series, while `net_usd` still counted them | `tests/test_metrics.py::test_trades_outside_evaluation_days_are_rejected` | `daily_pnl()` raises instead (`metrics.py:29`) | None (callers already filtered) |
| D5 | Minor parity | `pine/asian_range_strategy.pine` | Pine could start a new signal bar on the very bar that contained an exit. Python skips that signal bar | Code review | `exitedNow` guard | Unknown until parity is run (§4) |
| D6 | Documentation | `asiabt/research.py:6`, README, Pine header | The 2024-07 → 2026-10 period was called "untouched" | — | Relabelled **previously inspected OOS (OOS-I)** everywhere, with a status note in RESULTS.md and IMPROVEMENT_LOG.md (§5) | Wording only |

New tests: 21. The suite now has **34 passing tests**, covering metrics, ambiguity, parity tooling,
pre-2020 conversion and the pre-registered decision rule.

## 2. Statistical limitations (Stage 1B/C)

**Metric definitions** (`asiabt/metrics.py` docstring). Everything is per contract, USD, net of costs.

| Basis | Metrics |
|---|---|
| Trade | avg, win rate, PF, and the trade-level `t_stat`. The t-stat assumes i.i.d. trades and is kept only for comparability |
| Trading day (zero-trade days included) | Sharpe (× √252), Newey–West t, day-block bootstrap CIs |
| Equity | Cumulative daily P&L from 0 at the start of **each** period. Drawdown is measured from a running peak that includes 0 |

**Daily-level inference for v3** (`results/eval/B_fade_v3.json` → `inference`). Day blocks of
ceil(T^⅓) = 8–12 days, 5,000 resamples.

| Period | Days | Mean $/day | t (trades, i.i.d.) | t (Newey–West, daily) | Lag-1 ACF | 95% CI mean $/day | 95% CI mean $/trade (day blocks) | Share of bootstrap means ≤ 0 |
|---|---|---|---|---|---|---|---|---|
| TRAIN | 727 | 54.9 | 1.80 | 1.61 | 0.03 | [−7, 126] | [−26, 440] | 0.047 |
| VAL | 370 | 45.5 | 1.81 | 1.88 | −0.05 | [−3, 93] | [−8, 337] | 0.031 |
| OOS-I | 570 | −23.0 | −0.48 | −0.47 | −0.04 | [−119, 72] | [−414, 255] | 0.689 |
| FULL | 1,667 | 26.2 | 1.20 | 1.14 | −0.01 | [−17, 72] | [−62, 254] | 0.123 |

* **Autocorrelation is small** (|lag 1–5| ≤ 0.15 for every reported strategy-period; the largest is B1 in VAL), so Newey–West and
  the i.i.d. t-stats agree closely. Independence wasn't what inflated confidence; selection was.
* **Every 95% CI of mean daily P&L includes zero** at the default block length. Block-length
  sensitivity is stored too (`*_b1`, `_b5`, `_b20`). At 20-day blocks the VAL CI is [5, 87]. That
  is one setting out of four and must not be cherry-picked.
* **Multiple testing.** Deflated Sharpe Ratio on TRAIN+VAL (`scripts/deflated_sharpe.py`). The
  trial-Sharpe dispersion comes from 2,592 fade configurations (sd of annualised SR = 0.33).
  v3's annualised SR is 1.15, with skew 1.4 and kurtosis 15.

  | Assumed independent trials N | 1 | 10 | 100 | 1,000 | 7,000 |
  |---|---|---|---|---|---|
  | Expected max SR under the null (annualised) | 0 | 0.52 | 0.83 | 1.07 | 1.24 |
  | DSR (v3) | 0.994 | 0.92 | 0.76 | 0.57 | 0.42 |
  | DSR (v1) | 0.97 | 0.78 | 0.54 | 0.34 | 0.22 |

  The ~7,000 configurations are highly correlated, so the effective N is unknown. DSR drops below 0.95
  once N exceeds about 5 (0.92 at 10, 0.87 at 20), so v3 is not significant at 95% for any plausible N. DSR does **not** account for design choices made before
  the grids, or for the OOS-I peeks. White's Reality Check / Hansen SPA weren't run, because the
  full return series of every trial weren't stored. That is listed as a protocol requirement.
* **Annualisation.** The data has 247–249 sessions per year (recorder outages) against the √252
  convention, a ≈ 1% Sharpe difference. Fourteen low-coverage days enter as zero-P&L days, a
  slight dilution.

## 3. Data and execution audit (Stage 3)

`scripts/integrity_data_exec.py` → `results/integrity/data_execution_audit.json`, plus `results/data_validation.json`.

| Check | Result |
|---|---|
| Timestamp labels | TOS snapshots → `resample(label="left")`, so a bar covers [t, t+1m). The independent set is labelled at bar **end** and is shifted −1 min (agreement 82% vs 33% unshifted) |
| Timezone / DST | Agreement is identical in EDT and EST months (81.8% / 81.6%) and collapses to 4.7% at ±60 min. Every DST-transition session starts at 18:00 NY (offset 0), except 2024-03-11, which started at 19:12 because of a recorder outage. That session fails the 90% range-coverage rule and isn't traded |
| Globex trading day | 18:00–17:00 NY. The 17:00 halt is excluded. No weekend-labelled sessions |
| Range completion / signal timing | The range uses bars opening in [start, end). Signals use completed bars; entry is at the next open. Property tests perturb all future bars and confirm earlier trades don't change |
| Rolls | TOS is unadjusted. Rolls happen only at the 18:00 boundary (no mid-session switches). Daily features use a back-adjusted series that doesn't leak the future (property test). 4 v3 trades fall on roll-gap days, with correct intraday P&L |
| Missing minutes / stale prices | The stale filter removed 162k minutes: 98k in the 17:00 halt, 1.6k on Saturdays, the rest holidays/outages. Only ~30 short stale runs fall inside 18:00–11:00 over 6.7 years. No entry was delayed by missing data. One time exit was filled 15 min late after a data gap |
| Snapshot vs true exchange OHLC | Range highs are understated by a median 0.5 pt (p90 2.75, p99 17). For v3 on identical days (2023-01 → 2025-12): 155 trades match, with P&L $29.5k on snapshot data vs $26.8k on true OHLC. **44 trades exist only on snapshot data (+$3.6k), 58 only on true OHLC (−$12.2k).** The signal set depends on sub-point differences in extremes. That fragility, not fill prices, is why true OHLC gives $69 vs $166 per trade |
| Stop and target in one bar | 0 of 202 v3 stop exits (0 of 217 for v1) had the target also traded through in the same minute. The stop-first rule never decided an outcome |
| Gaps through stops | Fill at the bar open minus slippage (tested). 5 v3 stop-gap exits in total |
| Limit fills | 1-tick trade-through. Because snapshot highs are understated, this is ≥ 1 tick conservative |
| Costs / contracts | NQ $20/pt with a 0.25 tick ($5). $5 round turn plus 1 tick per side ≈ $15 per round trip. v3 average gross $105.6 vs net $93.3. Stress $7 + 2 ticks. MNQ $2/pt with $1.30 round turn. All within typical 2026 retail all-in fees |
| Future data in features | None found. ATR14, SMA20/50 and 5-day return are lagged one day. The roll back-adjustment subtracts the current day's offset (property test `test_daily_features_use_only_past_days`) |
| Independent-data comparison | Reproduced: $69 (true) vs $166 (snapshot) per v3 trade, as reported before |

No volume or order-flow features were added: the primary dataset has no /NQ volume.

## 4. Python/Pine parity (Stage 4)

| Item | Status |
|---|---|
| Static analysis in TradingView's editor | Passed: 0 errors, 0 warnings across 328 lines, with a positive control |
| Full compile / Strategy Tester | **NOT VERIFIED** (needs a TradingView login) |
| Trade-level parity | **NOT VERIFIED.** `scripts/parity_compare.py` parses the TradingView *List of trades* export, matches trades by day, side and entry time, and classifies each as identical / adjustment / resolution / intrabar_exit / price_diff / unmatched (`tests/test_parity.py`). The manual protocol is in `docs/PINE.md` |
| Known material differences | (1) Chart resolution, measured in Python with `scripts/parity_resolution.py`: 5-min bars give the same 472 signals, 13 different exit reasons, −$9/trade. (2) TradingView's intrabar path assumption instead of stop-first. That's irrelevant on 1-min data here (0 decisive cases) but may matter on 5-min charts. (3) Rejection checks use the signal close instead of the next open. (4) TradingView continuous-contract adjustment changes ATR around rolls, so run unadjusted. (5) TradingView exchange bars vs TOS snapshot bars change the *signal set* (see §3). That is the largest expected source of divergence |

## 5. Validation protocol corrections (Stage 5)

* 2024-07 → 2026-10 is **previously inspected (OOS-I)**. It was viewed when v1 was frozen and after
  every improvement cycle, and full-sample baseline smoke tests were run before the split was
  fixed. It is no longer a holdout. Corrected in `asiabt/research.py:6-13`, `README.md`, the Pine
  header, and status notes in `docs/RESULTS.md` and `docs/IMPROVEMENT_LOG.md`.
* No parameter, filter or strategy was chosen from OOS-I in this audit. No new broad sweep was
  run. The 2,592-config re-scoring in `deflated_sharpe.py` measures dispersion only and selects nothing.

## 6. Independent pre-2020 data (Stage 6): plan, not executed

**Recommendation.** Databento `GLBX.MDP3`, schema `ohlcv-1m` plus `definition`, symbols `NQ.FUT`
(parent), 2010-06-06 → 2019-12-31.

| Question | Answer |
|---|---|
| Coverage / timeframe | CME Globex MDP3 from 2010-06-06 (dataset start). 1-minute bars aggregated from exchange trades, ≈ 9.5 years / ~2,400 sessions |
| True OHLCV and contract IDs | Yes. Bars are built from trades and include volume. Each record has an `instrument_id`, and raw symbols (e.g. `NQH5`) come from `definition` (expirations). Timestamps are UTC nanoseconds of bar open |
| Licensing | Databento's subscriber terms: internal research use. Raw data must **not** be committed or redistributed (`data/` stays git-ignored) |
| Estimated cost | Pay-as-you-go, published "from $0.50/GB". New accounts get $125 of historical credit. A rough size estimate is ~0.3–1 GB for all outright NQ contracts' 1-min bars, i.e. single-digit dollars, likely within the credit. **This estimate is unverified.** The exact amount comes from `metadata.get_cost`, which `scripts/fetch_databento_nq.py` prints and stops on unless `--approve-cost-usd` is given |
| Storage / processing | < 1 GB raw, ~60 MB as front-month parquet. Conversion and evaluation take minutes |
| Separation from selection | The rules are frozen (`B_fade_v3r1` primary, `B_fade_v1r1` secondary). Conversion rules are coded and unit-tested before acquisition (`asiabt/independent.py`). The decision rule is written in `docs/PREREGISTRATION.md` and coded in `scripts/evaluate_independent.py::verdict` (tested). The fetcher refuses end dates after 2019-12-31 and the evaluator refuses bars after 2019-12-31 |
| Alternatives | **FirstRate Data NQ**: 1-min from 2008, individual contracts from NQZ08, unadjusted / absolute / ratio continuous; $99.95/yr updates, one-time price not shown; timezone and bar construction not documented, so the free sample must be validated first. **CME DataMine**: official Time & Sales / BBO, monthly or annual subscription, heavier processing. **Interactive Brokers**: needs an account; history depth for expired futures is limited |

Nothing was purchased, no API key was used and no paid request was made.

## 7. Research protocol (Stage 7)

See [`PREREGISTRATION.md`](PREREGISTRATION.md). It covers hypotheses first, frozen baselines, a
written grid of ≤ 200 configurations per hypothesis, chronology with a once-opened holdout,
base and stressed costs, sensitivity, long/short, by year, daily equity from 0, daily-level
inference, DSR across N plus Reality Check/SPA when trial series are stored, no volume features,
and parity before paper trading. Configurations ever evaluated: ≈ 7,000 in the original research,
plus 2,592 re-scored for the DSR variance (measurement only).

## 8. Reproduction

```bash
pip install -e ".[test]" && python -m pytest -q             # 34 tests
python scripts/integrity_metrics.py      # D1 effect on frozen trades + daily inference -> results/integrity/metric_corrections.csv
python scripts/integrity_ambiguity.py    # D2 frequency/effect -> results/integrity/ambiguity.csv
python scripts/integrity_data_exec.py    # Stage 3 -> results/integrity/data_execution_audit.json
python scripts/evaluate.py && python scripts/walk_forward.py && python scripts/robustness.py && python scripts/make_report.py
python scripts/integrity_before_after.py # -> results/integrity/before_after.csv (vs results/baseline_50f822f)
python scripts/deflated_sharpe.py        # -> results/integrity/deflated_sharpe.json
python scripts/parity_resolution.py      # -> results/parity/resolution.json
NODE_PATH=$(npm root -g) node scripts/lint_pine_tradingview.js pine/asian_range_strategy.pine
# after a TradingView export:  python scripts/parity_compare.py --tv <export.csv> --py results/eval/trades_B_fade_v3r1.csv
# after approval of the data spend: fetch_databento_nq.py -> build_front_month.py -> evaluate_independent.py
```

## 9. Scores after the audit

**Code quality: 9.0 / 10.** Unverified items are marked.

| Item | Score | Reason |
|---|---|---|
| Correctness and compilability | 1.5 / 2 | 34 tests, two defects fixed with reproducing tests, frozen results reproduce bit-for-bit. Pine passes static analysis; **compile and Strategy Tester run are unverified** |
| Execution and risk logic | 1.5 / 2 | Audited end to end (§3). Stop-first never decisive. **Python/Pine parity is unverified** |
| Repainting and look-ahead | 2 / 2 | Property tests for future perturbation and lagged features. Ambiguity rule uses only past 1-minute data |
| Readability and configurability | 2 / 2 | Minimal, reviewable diffs. Frozen configs untouched; corrected semantics are appended revisions |
| Diagnostics, testing, documentation | 2 / 2 | Audit scripts, before/after, daily inference, parity tooling with tests, pre-registration |

**Evidence quality: 7.0 / 10.** Down from 7.5: the audit found the evidence weaker than stated.

| Item | Score | Reason |
|---|---|---|
| Data quality and realistic costs | 1.0 / 2 | Costs are realistic. But snapshot-derived bars change **which** trades occur (§3), and in-sample performance halves on true OHLC |
| Out-of-sample and walk-forward | 1.0 / 2 | The walk-forward exists, but there is no pristine holdout (OOS-I was inspected). The independent pre-2020 test is planned, not run |
| Robustness across parameters | 1.0 / 2 | The in-sample plateau doesn't carry over. DSR < 0.95 for N ≳ 5 |
| Sample size and regimes | 1.5 / 2 | 2020–2026, 1,667 sessions. Final strategy ≈ 470 trades. All daily CIs include 0 |
| Transparency and reproducibility | 2 / 2 | Before-state preserved, every number scripted, defects and their (small) effects disclosed |
