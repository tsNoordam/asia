"""Pre-registered independent evaluation of FROZEN strategies on pre-2020 NQ
exchange data (docs/PREREGISTRATION.md). NOT YET RUN: the data has not been
acquired (needs user approval for the Databento spend).

Steps (all fixed in advance):
  1. data/nq_exchange_pre2020_1m.parquet from scripts/build_front_month.py
     (Databento GLBX.MDP3 ohlcv-1m -> asiabt.independent rules).
  2. Refuse to run if any bar is after 2019-12-31.
  3. Evaluate the frozen configs below UNCHANGED with base and stressed costs.
  4. Apply the pre-registered criteria in `verdict()` and write
     results/independent/report.json. No parameter may be changed after the
     results are seen; any later idea needs new, unseen data.

Usage: python scripts/evaluate_independent.py [--data data/nq_exchange_pre2020_1m.parquet]
"""
import argparse
import json
import pathlib
import sys

from asiabt.data import build_grid, load_minutes
from asiabt.engine import Costs, Params, run
from asiabt.metrics import by_year, inference, summarize

PRIMARY = "B_fade_v3r1"
SECONDARY = ["B_fade_v1r1"]
REPORT_ONLY = ["B_fade_v3", "B_fade_v1", "B1_simple_breakout", "B2_simple_fade", "B4_eu_open_long_00_04", "A_breakout_both"]
STRESS = Costs(commission_rt=7.0, slip_ticks=2.0)
LAST_DAY = "2019-12-31"
T_CRIT = 2.24  # Newey-West t; Bonferroni across the 2 tested hypotheses (v3r1, v1r1), one-sided alpha 0.0125


def verdict(base_inf: dict, stress_inf: dict, years: list, long_avg: float, short_avg: float) -> dict:
    """Pre-registered decision rule for one strategy."""
    primary = (base_inf.get("daily_t_nw", 0) > T_CRIT and base_inf.get("daily_mean_ci95", [0, 0])[0] > 0)
    secondary = {
        "stress_mean_daily_positive": stress_inf.get("daily_mean_usd", 0) > 0,
        "positive_years_at_least_60pct": sum(1 for y in years if y["net_usd"] > 0) >= 0.6 * max(len(years), 1),
        "long_and_short_mean_trade_positive": long_avg > 0 and short_avg > 0,
    }
    return {"primary_pass": bool(primary), "secondary": secondary,
            "supported": bool(primary and all(secondary.values()))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/nq_exchange_pre2020_1m.parquet")
    a = ap.parse_args()
    if not pathlib.Path(a.data).exists():
        sys.exit(f"{a.data} not found: acquire data first (docs/AUDIT.md §8). Nothing evaluated.")
    m = load_minutes(a.data, stale_run=0)  # exchange bars: no stale-snapshot filter
    if str(m.index.max().date()) > LAST_DAY:
        sys.exit("data extends past 2019-12-31; refusing (would overlap the research sample)")
    g = build_grid(m)
    cfg = json.loads(pathlib.Path("config/strategies.json").read_text())
    cfg = {**cfg["baselines"], **cfg["candidates"]}
    rep = {"data": a.data, "days": len(g), "first_day": str(g.days.min().date()), "last_day": str(g.days.max().date()),
           "strategies": {}}
    for n in [PRIMARY] + SECONDARY + REPORT_ONLY:
        p = Params(**cfg[n])
        tb, ts = run(g, p), run(g, p, STRESS)
        s, ib, i_s = summarize(tb, g.days), inference(tb, g.days), inference(ts, g.days)
        yrs = by_year(tb).reset_index().to_dict(orient="records")
        la = tb.loc[tb.side > 0, "usd"].mean() if len(tb) else 0.0
        sa = tb.loc[tb.side < 0, "usd"].mean() if len(tb) else 0.0
        entry = {"summary": s, "inference": ib, "stress_inference": i_s, "by_year": yrs}
        if n in [PRIMARY] + SECONDARY:
            entry["verdict"] = verdict(ib, i_s, yrs, la, sa)
        rep["strategies"][n] = entry
        print(n, entry.get("verdict", ""), {k: s.get(k) for k in ("trades", "avg_usd", "t_stat")})
    out = pathlib.Path("results/independent")
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
