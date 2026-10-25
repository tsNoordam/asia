# Results and candidate comparison

Full tables, including by-year, long/short, cost stress, sensitivity, walk-forward windows and
robustness checks, are generated into [`RESULTS_TABLES.md`](RESULTS_TABLES.md). This page
summarises them. All figures are per NQ contract after base costs ($5 round turn + 1 tick of
slippage per side on market/stop orders). Splits: TRAIN 2020-01 → 2022-12, VAL 2023-01 → 2024-06,
OOS 2024-07 → 2026-10 (previously inspected; see note below). Max drawdowns were recomputed with the
corrected zero-baseline formula; only one reported value changed (AUDIT.md §1).

> **Status of the OOS period (added by the integrity audit, see [AUDIT.md](AUDIT.md)).** The period
> 2024-07 → 2026-10 is a **previously inspected out-of-sample period ("OOS-I")**, not an untouched
> holdout. It never chose a parameter, but its results were viewed when v1 was frozen and after
> each improvement cycle, and full-sample baseline smoke tests were run before the split was fixed.
> It must not be used to select parameters, filters or strategies. A genuinely independent test
> needs new data (pre-2020, see AUDIT.md §8) or future live/paper data.

## Headline

**No candidate has a robust, statistically defensible edge after costs.**

* **Breakout (A).** Negative or beta-like in every honest test. The simple breakout baseline
  loses in all three periods (t −1.01 / −0.41 / −0.56).
* **Mean reversion (B).** The fade after a failed excursion was the strongest candidate
  in-sample (v3: TRAIN t 1.80, VAL t 1.81). It **fails out-of-sample** (−$81/trade, t −0.48) and
  in walk-forward (−$32/trade, t −0.36).
* **Regime-switching hybrid (C).** Worse than the pure fade on the selection data, so it was
  rejected. Its OOS result (+$84/trade, t 0.58) is not significant and wasn't used to change
  that decision.
* **Passive benchmark.** The best performer is a benchmark we didn't develop: long NQ from 00:00
  to 04:00 ET (the "EU-open drift"). It's positive in all three periods (t 1.48 / 0.44 / 0.77,
  full-sample t 1.56, Sharpe 0.61), but also not significant, and its authors report it has
  faded since 2021.

## Performance table: baselines, validation and OOS

| Strategy | TRAIN n / avg $ / t | VAL n / avg $ / t | OOS n / avg $ / t | Full PF | Full Sharpe | Full max DD $ |
|---|---|---|---|---|---|---|
| B0 no trade | 0 | 0 | 0 | – | – | 0 |
| B1 simple breakout (18–00 range, close beyond, stop opposite side, flat 11:00) | 630 / −88 / −1.01 | 336 / −37 / −0.41 | 505 / −83 / −0.56 | 0.93 | −0.44 | −125,710 |
| B2 simple fade (any excursion, close back inside, target mid) | 591 / 1 / 0.03 | 324 / 1 / 0.05 | 472 / −58 / −1.10 | 0.95 | −0.32 | −44,792 |
| B3 timed long 00:00→11:00 | 696 / −25 / −0.24 | 359 / 96 / 0.85 | 554 / −7 / −0.04 | 1.01 | 0.04 | −132,555 |
| B4 timed long 00:00→04:00 (EU open) | 695 / 60 / 1.48 | 359 / 16 / 0.44 | 552 / 53 / 0.77 | 1.12 | 0.61 | −28,030 |
| B5 timed long 02:00→16:00 | 678 / −39 / −0.26 | 350 / 350 / 2.18 | 539 / 77 / 0.32 | 1.06 | 0.30 | −116,610 |
| A breakout, best pooled plateau (long only) | 343 / 33 / 0.21 | 198 / 275 / 1.54 | 267 / −39 / −0.16 | 1.05 | 0.24 | −51,979 |
| A breakout, same rules both sides | 567 / −114 / −0.91 | 307 / 41 / 0.30 | 437 / −56 / −0.28 | 0.96 | −0.25 | −119,698 |
| C hybrid v1 | 380 / 76 / 0.80 | 235 / 16 / 0.18 | 279 / 84 / 0.58 | 1.08 | 0.38 | −30,397 |
| B fade v1 | 229 / 172 / 1.68 | 120 / 69 / 0.73 | 181 / 20 / 0.12 | 1.14 | 0.49 | −28,727 |
| B fade v2 | 195 / 170 / 1.54 | 100 / 166 / 1.79 | 156 / −93 / −0.54 | 1.12 | 0.38 | −34,986 |
| **B fade v3 (final)** | 206 / 194 / 1.80 | 101 / 167 / 1.81 | 161 / −81 / −0.48 | 1.14 | 0.47 | −33,630 |

### Final candidate (v3): more detail

| Metric | TRAIN | VAL | OOS |
|---|---|---|---|
| Net profit $ | 39,896 | 16,838 | −13,090 |
| Profit factor | 1.34 | 1.49 | 0.92 |
| Win rate | 54.9% | 64.4% | 46.0% |
| Avg winner / avg loser $ | 1,377 / −1,244 | 788 / −955 | 1,979 / −1,833 |
| Expectancy $/trade | 194 | 167 | −81 |
| Sharpe (daily, ann.) | 1.08 | 1.48 | −0.32 |
| Max drawdown $ | −16,763 | −5,210 | −33,630 |
| Time in market | 4.1% | 3.7% | 4.3% |
| Long: n / net $ / t | 102 / 16,218 / 1.00 | 45 / 11,160 / 1.73 | 92 / −17,532 / −0.84 |
| Short: n / net $ / t | 104 / 23,678 / 1.57 | 56 / 5,678 / 0.85 | 69 / 4,441 / 0.25 |
| Bootstrap 95% CI of mean trade $ | [−13, 406] | [−10, 346] | [−407, 243] |

By year: 2020 −$1.7k, 2021 +$23.7k, 2022 +$17.9k, 2023 +$11.4k, 2024 +$3.8k, 2025 +$15.9k,
**2026 −$27.4k**. The OOS loss is concentrated in 2026. We did **not** use that to re-tune anything.

## Breakout vs mean reversion: detailed comparison

| Aspect | A: Asian-range breakout | B: failed-breakout fade |
|---|---|---|
| Hypothesis | A close beyond the completed range predicts continuation into the late morning | An excursion beyond the range that closes back inside predicts a return across the range |
| Prior evidence | Against: arXiv MNQ study (Asia expansion bars reverse), net-zero ORB replications, losing FX London-breakout backtests | For the mechanism: Osler's stop/take-profit clustering, short-horizon reversal (arXiv). No cost-inclusive NQ evidence |
| Sweep breadth | 1,296 configs; 20% positive in TRAIN | 2,592 + 2,592 configs; 53% / 57% positive in TRAIN / VAL |
| TRAIN→VAL persistence | Rank correlation −0.24, so no persistence | Rank correlation +0.23, weak persistence |
| Best plateau | Long-only, held to 16:00. Equals the passive long benchmark (B5), i.e. beta | 18:00–00:00 range, excursion 0.075–0.125 ATR, target opposite side |
| Long vs short | Shorts lose in all periods (t −1.29 / −1.70 / −0.60). Longs ride the trend | Both sides positive in TRAIN and VAL (v1). Both ≈ 0 OOS |
| Range-width regime | Positive only in the narrowest tercile (< 0.207 ATR) | Positive across terciles in TRAIN. Mixed in VAL |
| Cost sensitivity | Already negative gross | Gross → base costs −$12/trade. The edge was large relative to costs in-sample, so cost isn't why it fails |
| OOS (fixed rules) | −$56/trade (both sides) | v1 +$20, v3 −$81 |
| Walk-forward 2022–2026 | +$31/trade, t 0.21 | −$32/trade, t −0.36 |
| Independent data (true OHLC, 2023–2025) | n/a | v3 $69/trade (t 0.64) vs $166 (t 1.53) on TOS bars for the same days. **Results depend on the data source** |
| Out-of-market (/ES) | n/a | v1: t 1.04 / 0.53 / 1.11. v3: t 0.46 / 0.09 / 1.10. Small and not significant |
| Verdict | **Rejected**: no edge beyond beta | **Strongest candidate, but not validated.** Paper-trade research only |

## Session definitions compared (final rules, `results/robustness.json`)

| Asian range | TRAIN avg / t | VAL avg / t | OOS avg / t |
|---|---|---|---|
| 18:00–00:00 (chosen) | 194 / 1.80 | 167 / 1.81 | −81 / −0.48 |
| 18:00–02:00 | 220 / 1.73 | 94 / 0.90 | −130 / −0.65 |
| 20:00–02:00 | 62 / 0.53 | 106 / 1.12 | −9 / −0.04 |

## MNQ

MNQ uses the same price series at $2/pt. With a $1.30 round turn and 1 tick ($0.50) of
slippage per side, v3 averages $19 / $16 / −$9 per trade (TRAIN / VAL / OOS). Costs are a
slightly larger share of each trade than on NQ, but the conclusion is unchanged. MNQ is only a
way to paper/live-test the same logic at 1/10 of the notional.

## What the evidence supports

1. The Asian range is breached on almost every session, and re-entry after the first break is
   nearly certain (≈97%), as vendor statistics claim. **But** direction at 11:00 is a coin
   flip, so the re-entry statistic can't be traded on its own.
2. Simple Asian-range breakouts on NQ lose money after costs, consistent with the literature.
3. A conditional fade (meaningful but not extreme excursion, then a close back inside) produced
   in-sample results that look like an edge. Its profits shrank in every later period (TRAIN
   → VAL → OOS for v1), it failed walk-forward, and it is weaker on true-OHLC data. The most
   likely explanation is selection over ~7,000 configurations, not a persistent market inefficiency.

## Still speculative

* Whether the fade has a small real edge that a ~160-trade OOS sample can't detect. The
  bootstrap CIs are wide enough to include both a useful edge and a loss.
* Whether volume-confirmed breakouts behave differently. The primary data has no /NQ volume,
  so this wasn't tested.
* Whether the 2026 OOS losses reflect a new market regime or just variance.
