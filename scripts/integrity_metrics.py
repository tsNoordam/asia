"""Integrity audit, Stage 1: effect of the metric fixes on EXISTING trades.

Re-scores the frozen trade lists of commit 50f822f
(results/baseline_50f822f/eval/trades_*.csv) per period with
  * the old drawdown formula (running peak started at the first day's equity),
  * the corrected formula (running peak includes the 0 starting equity),
and adds daily-level inference (Newey-West t, day-block bootstrap CIs) next to
the trade-level i.i.d. t-stat. Trades are unchanged, so every difference is a
pure metric correction.

Usage: python scripts/integrity_metrics.py -> results/integrity/metric_corrections.csv
"""
import glob
import pathlib

import pandas as pd

from asiabt.metrics import daily_pnl, inference, max_drawdown, summarize
from asiabt.research import load_grid, period

BASE = pathlib.Path("results/baseline_50f822f/eval")
OUT = pathlib.Path("results/integrity")


def old_drawdown(daily: pd.Series) -> float:
    """Formula used up to 50f822f (kept only to quantify the correction)."""
    eq = daily.cumsum()
    return float((eq - eq.cummax()).min()) if len(eq) else 0.0


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    g = load_grid()
    rows = []
    for f in sorted(glob.glob(str(BASE / "trades_*.csv"))):
        name = pathlib.Path(f).stem.replace("trades_", "")
        tr = pd.read_csv(f, parse_dates=["day"])
        for per in ("train", "val", "oos", "full"):
            sub = g if per == "full" else period(g, per)
            t = tr[tr["day"].isin(sub.days)]
            d = daily_pnl(t, sub.days)
            s = summarize(t, sub.days)
            inf = inference(t, sub.days)
            rows.append({
                "strategy": name, "period": per, "trades": len(t), "net_usd": round(float(t["usd"].sum()), 2),
                "max_dd_old": round(old_drawdown(d), 2), "max_dd_new": round(max_drawdown(d), 2),
                "dd_changed": abs(old_drawdown(d) - max_drawdown(d)) > 0.005,
                "first_day_pnl": round(float(d.iloc[0]), 2) if len(d) else 0.0,
                "sharpe": round(s.get("sharpe", float("nan")), 3),
                "trade_t_iid": round(s.get("t_stat", float("nan")), 3),
                "daily_t_iid": round(inf.get("daily_t_iid", float("nan")), 3),
                "daily_t_nw": round(inf.get("daily_t_nw", float("nan")), 3),
                "acf1": round(inf["acf"][0], 3) if "acf" in inf else float("nan"),
                "daily_mean_ci95": [round(x, 1) for x in inf.get("daily_mean_ci95", [])],
                "trade_mean_ci95_dayblock": [round(x, 1) for x in inf.get("trade_mean_ci95", [])],
                "p_boot_le0": inf.get("p_boot_le0"),
            })
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "metric_corrections.csv", index=False)
    ch = df[df["dd_changed"]]
    print(f"{len(ch)} of {len(df)} strategy-periods change max drawdown:")
    print(ch[["strategy", "period", "first_day_pnl", "max_dd_old", "max_dd_new"]].to_string(index=False))


if __name__ == "__main__":
    main()
