# Phase 1 — Research and source inventory

Searched in October 2026: academic papers (SSRN, arXiv, JFE/JFQA, NY Fed), TradingView
community scripts, practitioner blogs (MQL5, tradingstats.net, Edgeful, QuantifiedStrategies),
forums, and data vendors. **GitHub:** web searches for Asian/overnight-range breakout
repositories on NQ/MNQ found no public repository with tested rules and results. Every hit
was a TradingView script, a vendor page or a freelance job post. (This session's GitHub API
access only covers the project repository, so GitHub code search wasn't used.)

Evidence labels used below:
* **Verified (here):** reproduced in this project on our own data (`scripts/stats_asia.py`, backtests).
* **Peer-reviewed:** published in a refereed journal; not re-run here unless stated.
* **Author claim:** numbers reported by the source and not independently checked.
* **Anecdotal:** forum posts, indicator descriptions, marketing.

## Ranked source table

Ranked by how much each source matters to this project: relevance to NQ Asian-session
ranges, and evidence quality.

| # | Source (author, date) | Market / instrument | Session / TZ | Mechanical rules | Data / sample | Reported results | Costs / rolls / look-ahead | Evidence type | Reproduced here? | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | [Asia Range Sweep & Reversion: 12-Year Study](https://tradingstats.net/asia-range-cascade-12-year-backtest/) (TradingStats, no author named, 1 May 2026) | NQ, ES, YM, RTY futures | Asia 20:00–02:00 ET, London 02:00–08:00 ET, America/New_York | No trading rules: conditional probabilities only. Break = London bar beyond Asia H/L. Extension ladder 0.1–1.0× range | "CME-licensed" 1-min OHLCV, 2014-02 → 2026-04, NQ 3,131 sessions | NQ: break rate 93.3%, bilateral 23.3%, "reversion" 96.8%; P(ext ≥ 1.0× range) 29.4%; recent 6-mo 17.0% | Not trading results, so no costs. No OOS (stated). Full-sample probabilities | Author claim (statistics) | **Partly verified.** Our 20:00–02:00 range on TRAIN+VAL: break before 08:00 = 94.7%, re-entry after first break = 97.2%. **But** price at 11:00 is beyond the first-broken side 50.1% of the time, so "reversion" says nothing about direction | "Reversion" undefined; a 1-min close back inside is almost certain whatever the eventual direction |
| 2 | [Structural Limits of OHLCV-Based Intraday Momentum Signals in MNQ Futures](https://arxiv.org/abs/2605.04004) (M. Mesfin, arXiv, v1 5 May 2026, v3 15 Sep 2026) | MNQ | Includes Asia 20:00–02:00 ET expansion bars, London, RTH | 14 signal families incl. Asia expansion bars (5-min range > k × 20-bar avg), ORB, gap continuation | 5-min OHLCV 2021–2025, 947 days, expanding walk-forward, OOS 2023/24/25 | None of 14 families passed. Asia expansion bars **reverse** (t ≈ −11.5 at 1.5×, one-bar horizon). Gross edges 0.07–1.5 pts vs 2.0-pt friction floor | Friction floor 2.0 pts; permutation tests; OOS folds | Preprint (not peer-reviewed) | No (different signal) | Single author; one-bar horizon; data vendor not on abstract page |
| 3 | [Market Return Around the Clock: A Puzzle](https://ideas.repec.org/a/cup/jfinqa/v58y2023i3p939-967_1.html) (O. Bondarenko & D. Muravyev, JFQA 58(3), 2023) | E-mini S&P 500 (ES) futures | "EU-open" 23:30–03:30 ET | Hold long only during EU-open window | Tick data 2004–2018 | Whole equity premium earned around EU open; Sharpe ≈ 1.6, survives costs (per abstract) | Costs discussed (abstract) | Peer-reviewed | Benchmark tested: long 00:00→04:00 ET on NQ | ES not NQ; see #4 for post-publication decay |
| 4 | [The Overnight Drift](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf) (N. Boyarchenko, L. Larsen, P. Whelan, NY Fed SR 917; RFS) + [The Disappearing Overnight Drift](https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/) (Liberty Street Economics, 1 Jul 2026) | ES; text says NQ and YM look the same | 02:00–03:00 ET | Long ES 02:00–03:00 | 1998–2020; post-publication 2021–2025 | 02:00–03:00 earned ≈ 3.7%/yr pre-2021, gross Sharpe 1.0, **negative after bid-ask**. Since 2021 ≈ 0, also for NQ | Spreads included in SR 917 | Fed working paper + blog | Benchmark tested | Evidence that a time-of-day edge can decay after publication |
| 5 | [Can Day Trading Really Be Profitable?](https://papers.ssrn.com/abstract=4416622) (C. Zarattini & A. Aziz, SSRN Apr 2023) | QQQ / TQQQ | RTH first 5-min bar | First 5-min candle direction → enter at open of 2nd bar, stop at far side of bar 1, target 10R or EOD | 2016–2023 | 33% annual alpha net of commissions (author claim) | Commission only, no spread/slippage, no OOS | SSRN working paper | No (RTH ORB, not Asian session) | Shows how an opening-range idea can look better than it is when costs are left out |
| 6 | [The opening-range breakout paper, replicated on five indices: gross reproduced, net zero](https://www.mql5.com/en/blogs/post/776235) (T.-P. Krueger, MQL5 blog, 25 Sep 2026) | NQ, SPX, Dow, DAX, FTSE CFDs | RTH | Zarattini–Aziz rules unchanged | Own minute data 2015–2026 | NQ gross +0.147 R, **net +0.002 R**. Edge vs random direction ≈ 0.1 R ≈ cost | Spread + slippage per trade | Independent replication (blog) | No | CFD data, single author |
| 7 | [Intraday momentum: the first half-hour return predicts the last half-hour](https://doi.org/10.1016/j.jfineco.2018.05.009) (L. Gao, Y. Han, S. Z. Li, G. Zhou, JFE 129, 2018) | SPY + 10 ETFs | Prior close→10:00 ET; last 30 min | Sign of first half-hour return → trade last half-hour | 1993–2013 | Significant, stronger on volatile / high-volume / news days | Costs considered (ETF) | Peer-reviewed | No | Different window. Motivates trend/volatility regime variables |
| 8 | [Currency Orders and Exchange-Rate Dynamics](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr125.pdf) (C. Osler, NY Fed SR 125, 2001; JF 2003) | FX (one dealer's order book) | n/a | Mechanism: take-profit orders cluster at round levels (reversal); stop-losses just beyond them (acceleration) | Bank order data | Stop-loss clusters → price cascades once a level breaks. Take-profits → reversals before the level | n/a | Peer-reviewed | No | Mechanism for both "breakout" and "false breakout" at salient levels, but FX only |
| 9 | [London Breakout on Gold: 3.7 Years of Backtests](https://www.mql5.com/en/blogs/post/777540) (S. M. N. R. Pinjori, MQL5, 13 Oct 2026) | XAUUSD | Asian range 03:00–08:00 broker time; flat 21:00 | Buy/sell stop beyond Asia H/L (OCO). SL opposite side capped 0.6%, TP 2.5R, BE at 1.5R, 1 trade/day, range filter 0.30–1.60% | MT5 real ticks 2023-01 → 2026-09, 2 brokers | PF 1.38, 715 trades, DD 17–19%. 2026 OOS PF 1.61 on 157 trades | Costs not stated. Parameters chosen on 2023–25 | Author claim | No (gold) | Failure modes reported: tight in-range stops get hit by noise; very narrow ranges give false breaks; very wide ranges mean the move already happened |
| 10 | [Backtrex: London breakout EUR/USD](https://backtrex.com/en/backtests/london-breakout-eur-usd) and [GBP/USD](https://backtrex.com/en/backtests/london-breakout-gbp-usd) (vendor, 2026) | EURUSD, GBPUSD | Asian range → London | Fixed SL, TP = 2× SL | 2016–2026 | EURUSD PF 0.87 (1,230 trades); GBPUSD PF 0.72 (2,432 trades) | Partly stated | Vendor backtest | No | Contradicts #9: the simple Asian breakout loses on major FX |
| 11 | [AI MES Asian Session Strategy](https://www.tradingview.com/script/HR3TVGbS-AI-MES-Asian-Session-Strategy/) (TradingView user lylerh, open source) | MES | Range = first 30 min after 18:00 ET | Breakout (close outside + volume + RSI, stop inside range, 1.5R) **competes** with fade (touch + RSI extreme + close back inside, stop beyond extreme, target midpoint) | None | None | None | Anecdotal / code | Concept tested (Candidate C) | No results; RSI/volume thresholds partly unspecified |
| 12 | [Session Liquidity Reversion Strategy (Asia Range False Breakout)](https://kr.tradingview.com/script/uHN2BQiV-Session-Liquidity-Reversion-Strategy-Asia-Range-False-Breakout) (TradingView, open source) | Generic (FX, indices, crypto) | Asia range; London/NY execution | Break beyond Asia range, fails, closes back inside + RSI confirmation → fade | None | None | None | Anecdotal / code | Concept tested (Candidate B) | No results |
| 13 | [Asian Box Breakout Strategy](https://th.tradingview.com/script/P1hYfpeB-Asian-Box-Breakout-Strategy/) (TradingView user waranyutrkm) | Generic | Asian session, UTC+7 default | Buy-stop/sell-stop beyond box (OCO), SL = daily ATR × mult, EOD flat, 1 trade/day | None | None | None | Anecdotal / code | Concept tested (Candidate A) | Sizes at 100% of equity; no results |
| 14 | [Edgeful: trading sessions explained](https://www.edgeful.com/blog/posts/trading-sessions-explained) (vendor blog) | NQ, ES | Asia 19:00–04:00 ET | None (descriptive) | 127 days | Asian session has the smallest range. NQ Asian range > 14-day ATR on 11.8% of days | n/a | Vendor statistic | Consistent: median Asian range ≈ 0.22–0.26 × daily ATR here | 6-month sample |
| 15 | NQ Stats session indicators ([ALN Sessions](https://in.tradingview.com/script/KNTFWlm2-ALN-Sessions-NQ-Stats-x-CantoLab/)) | NQ | Asia 20:00–02:00, London 02:00–08:00 ET | Probabilities that session H/L get swept later | "10 years" / "2021–2025, 1,283 days" | e.g. 76.7% NY hits London high first when NY opens above London midpoint | n/a | Author claim | No | Sample definitions vary between descriptions |
| 16 | ICT "Judas swing" / "Power of Three (AMD)" ([guide](https://takeprofitapp.com/en/learn/ict-judas-swing-explained)) | FX, indices | Varies: 02:00–05:00 ET or 03:00–05:30 ET | Sweep of Asian H/L in London, then reversal | None | "65–75% reversal rate" (no method) | None | Anecdotal / marketing | Mechanical core (sweep + close back inside) = Candidate B | **No statistical evidence found** for AMD |
| 17 | [Holmberg, Lönnbark & Lundström: Assessing the profitability of intraday opening range breakout strategies](https://ideas.repec.org/p/hhs/umnees/0845.html) (FRL 10(1), 2013) | Crude-oil futures | Opening range | ORB | — | Abstract only (full text not retrieved) | — | Peer-reviewed | No | Results not verified here |

## What the evidence supports, and what is speculative

**Supported by more than one independent source:**
1. NQ's Asian session is the quietest part of the day. Its range is small next to the daily
   ATR (Edgeful; here the median is 0.22–0.26 × ATR14).
2. The Asian range gets breached on almost every session before the New York open (≈ 94%),
   and the first breach is almost always re-entered at some point (≈ 97%). This was reproduced
   here. Because a 1-minute close back inside is so common, the re-entry statistic **can't be
   traded on its own**: on half the sessions, price at 11:00 sits beyond the side that broke first.
3. Simple breakout systems on index and FX sessions mostly disappear after realistic costs
   (#2, #6, #10). The gross edges people report are about the size of 1–2 ticks of friction.
4. Time-of-day return effects around the European open were real in ES before 2021 (#3, #4).
   The authors' own update says they've faded since 2021, NQ included. That window is a
   benchmark here, not a strategy.

**Speculative or unsupported:**
* AMD / Judas-swing claims: no reproducible statistics found.
* Vendor and TradingView strategy results: none publish a cost-inclusive, out-of-sample record on NQ.
* "Fade the false breakout" has a plausible mechanism (Osler's order clustering, #8), and #2
  found short-horizon reversal of Asia expansion bars. Nobody has shown it survives costs on NQ
  over a holding horizon. This project tests that.

## Hypotheses carried into testing

* **H-A (breakout):** a confirmed close beyond the completed Asian range predicts continuation
  until the late morning that is large enough to cover ≈ 0.75 pt of round-trip friction.
  The literature leans against it.
* **H-B (mean reversion):** an excursion beyond the range followed by a close back inside
  predicts a move toward the range midpoint or the opposite side before the stop beyond the
  excursion extreme is hit. Mechanism: #8, short-horizon evidence: #2.
* **H-C (regime):** narrow (compressed) Asian ranges favour breakouts and wide ranges favour
  fades. Taken from the range-filter observations in #9 and #11. Tested only after A and B.
