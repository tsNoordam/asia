# Version-by-version improvement log

**Protocol, fixed before cycle 1.** Every change has to come from a written hypothesis about a
failure mode seen in TRAIN+VAL trades. A change is adopted only if (a) the pooled TRAIN+VAL
t-stat of the mean trade improves, (b) VAL does not get worse, and (c) the parameter values one
grid step either side also beat the previous version, so a single lucky value isn't enough.
The OOS period is evaluated after every cycle **for reporting only**. It never decides adoption.
At most four cycles.

Configurations live in `config/strategies.json` (append-only). Numbers are base costs, per NQ
contract. Regenerate them with `python scripts/evaluate.py <name>`.

## Pre-cycle: candidate selection (Phase 3)

| Step | What was done | Result |
|---|---|---|
| Descriptive stats | `scripts/stats_asia.py`, TRAIN+VAL | The Asian range breaks before 08:00 on 90–95% of sessions and is re-entered after the first break 97% of the time. Price at 11:00 is beyond the first-broken side only ~50% of the time |
| Sweep A (breakout) | 1,296 configs, 3 range definitions × cutoffs × flat times × tf × buffer × stop × target × side | 20% of configs profitable in TRAIN. TRAIN→VAL rank correlation **−0.24**. The best pooled plateau is long-only and equals market beta (it tracks the "long 02:00→16:00" benchmark) |
| Sweep B (fade) | 2,592 configs | 53% / 57% positive, rank correlation **+0.23**. Most robust region: range 18:00–00:00, excursion ≥ 0.10 × ATR, close back inside, target = opposite boundary |
| Sweep B2 (fade, focused) | 2,592 configs | Plateau at excursion 0.075–0.10 × ATR, direction both, target opposite |
| Candidate C (hybrid) | Narrow range (< 0.207 × ATR, TRAIN tercile) → breakout, else fade | Worse than pure fade: TRAIN t 0.80, VAL t 0.18. **Rejected** |

About 7,000 configurations were evaluated in total. With that many trials, a TRAIN or VAL
t-stat around 2 is what chance alone would produce, so the OOS and walk-forward results are
the ones that count.

## v1 — first working candidate (B_fade_v1)

Range 18:00–00:00 NY. Signals on 5-minute closes from 00:00 to 08:00. Requires an excursion
≥ 0.10 × ATR14 beyond the range, followed by a close back inside. Enter at the next open, stop
at the excursion extreme + 0.05 × ATR, target the opposite boundary, flat at 11:00, 1 trade per
session, both directions.

| | TRAIN | VAL | OOS |
|---|---|---|---|
| Trades / avg $ / t | 229 / 172 / 1.68 | 120 / 69 / 0.73 | 181 / 20 / 0.12 |

## Cycle 1 — breakout-strength cap → **v2 adopted**

* **Failure mode (TRAIN+VAL).** Losses are full stop-outs (avg −$1,280) that cluster in 2022.
  Performance falls as the excursion grows: 0.12–0.15 × ATR +$166/trade, 0.15–0.2 +$60,
  0.2–0.3 −$66.
* **Hypothesis H1.** Large excursions are genuine breakouts (completed stop cascades), so they
  shouldn't be faded. Cap the excursion.
* **Also tested, H2.** Only fade in the direction of the prior-day SMA20 trend.
* **Results (pooled TRAIN+VAL t).** v1 1.83. Cap 0.15: 2.52, but its neighbours 0.125 / 0.175
  are 1.68 / 1.66, so it fails (c). Cap 0.20: 2.00, but neighbour 0.175 fails. **Cap 0.225:
  2.13**, with neighbours 0.20 / 0.25 at 2.00 / 1.87 → passes. VAL improved from $69 to $166
  per trade. TRAIN dipped slightly (t 1.68 → 1.54). Trend filter: t 1.84, essentially
  unchanged, though max drawdown halved → not adopted.
* **v2 = v1 + max excursion 0.225 × ATR.**
* **OOS (reporting): v2 −$93/trade, t −0.54.** Worse than v1's +$20. The VAL improvement did
  not generalise.

## Cycle 2 — breakeven stop → **rejected, v2 kept**

* **Failure mode.** Stopped trades first move a median 0.28 R in favour (75th percentile 0.60 R).
* **Hypothesis.** Once price returns to the range midpoint or reaches k R, moving the stop to
  entry converts full losses into scratches.
* **Result (pooled t).** No breakeven 2.13. At midpoint −0.16, 0.5 R 0.58, 0.75 R 1.06,
  1.0 R 1.81. Worse at every level, and the same holds for v1. Winning fades usually come back
  to entry before reaching the target. **Rejected.**
* A volatility-expansion filter (ATR14 / ATR100 of prior days) was checked as a diagnostic
  before this cycle. It showed no consistent sign across TRAIN and VAL, so it was **never added**.

## Cycle 3 — second trade per session → **v3 adopted**

* **Failure mode.** About half of sessions break both sides by 11:00, but v2 allows one trade.
* **Hypothesis.** A second failed excursion after the first trade has exited is an independent
  opportunity.
* **Result (pooled t).** max_trades 2: 2.37. Neighbour max_trades 3: 2.31. VAL unchanged
  (t 1.79 → 1.81). Adopted. Only ~12 extra trades were added over TRAIN+VAL, so the gain rests
  on a small sample. Signal bar length was also checked: 3 / 5 / 10 / 15 minutes gave pooled
  t 1.82 / 2.13 / 2.09 / 1.97, so 5 is kept.
* **v3 = v2 + max 2 trades per session.**
* **OOS (reporting): v3 −$81/trade, t −0.48.**

## Cycle 4 — short-horizon time stop → **rejected, v3 kept (final)**

* **Hypothesis (from arXiv 2605.04004).** Asia-session expansion moves reverse over short
  horizons, so a time stop should capture the edge before it decays.
* **Result (pooled t).** Without a time stop 2.37. With a hold of 15 / 30 / 60 / 90 / 120 / 180
  minutes: −0.49 / 0.92 / −0.96 / −0.54 / 0.28 / 1.73. **Rejected.** The in-sample profit
  needs the full hold to the opposite boundary. A 15-minute hold nets ≈ $0 after costs, which
  matches the paper's finding that short-horizon gross edges sit below friction.

## Summary

| Version | Change | TRAIN avg / t | VAL avg / t | Pooled t | OOS avg / t | Decision |
|---|---|---|---|---|---|---|
| v1 | — | 172 / 1.68 | 69 / 0.73 | 1.83 | 20 / 0.12 | baseline candidate |
| v2 | max excursion 0.225 ATR | 170 / 1.54 | 166 / 1.79 | 2.13 | −93 / −0.54 | adopted (rule) |
| (c2) | breakeven at mid / R | ≤ 149 / ≤ 1.43 | ≤ 110 / ≤ 1.24 | ≤ 1.81 | n/a | rejected |
| v3 | max 2 trades / session | 194 / 1.80 | 167 / 1.81 | 2.37 | −81 / −0.48 | adopted (rule), **final** |
| (c4) | time stop 15–180 min | ≤ 141 / ≤ 1.86 | ≤ 31 / ≤ 0.52 | ≤ 1.73 | n/a | rejected |

**What went wrong.** The protocol improved TRAIN+VAL statistics, and every adopted change made
OOS *worse* than v1. That is the textbook signature of fitting noise in the validation period.
The walk-forward test (`results/walk_forward.json`) points the same way: re-selecting fade
parameters every 6 months from the trailing 24 months loses −$32/trade (t −0.36) from 2022 to 2026.
