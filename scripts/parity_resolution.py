"""Parity factor: chart resolution.

Runs the frozen fade rules on 5-minute bars (what the Pine strategy sees on a
5-minute chart with sigTf = 5) and compares with the 1-minute execution of the
Python engine on identical days. Signals are the same in both (5-minute signal
bars); only fills/exits are resolved more coarsely, plus the excursion-timing
used by the two-sided rule. This quantifies the resolution component of any
Python/Pine difference WITHOUT TradingView.

Usage: python scripts/parity_resolution.py -> results/parity/resolution.json
"""
import json
import pathlib

from asiabt.data import build_grid, load_minutes
from asiabt.engine import Params, run
from asiabt.metrics import summarize
from asiabt.research import SPLITS

CFG = json.loads(pathlib.Path("config/strategies.json").read_text())["candidates"]


def main():
    m1 = load_minutes("data/nq_tos_1m.parquet")
    m5 = m1.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    g1, g5 = build_grid(m1), build_grid(m5)
    # daily features must not depend on bar size; use the 1-minute ones on both
    g5 = g5.subset(g5.days.isin(g1.days))
    g1 = g1.subset(g1.days.isin(g5.days))
    g5.daily = g1.daily.copy()
    g5.coverage = g1.coverage.copy()
    out = {}
    for n in ("B_fade_v1r1", "B_fade_v3r1"):
        p = Params(**CFG[n])
        t1 = run(g1, p.replace(min_range_cov=0.0, min_trade_cov=0.0))
        t5 = run(g5, p.replace(min_range_cov=0.0, min_trade_cov=0.0))
        key = ["day", "side", "entry_off"]
        mm = t1.merge(t5, on=key, how="outer", suffixes=("_1m", "_5m"), indicator=True)
        both = mm[mm["_merge"] == "both"]
        r = {"note": "coverage filters disabled in both runs (5-minute grid has 1/5 of the slots)"}
        for per, (a, b) in SPLITS.items():
            days = g1.days[(g1.days >= a) & (g1.days <= b)]
            r[per] = {"1m": {k: summarize(t1[t1.day.isin(days)], days)[k] for k in ("trades", "avg_usd", "t_stat")},
                      "5m": {k: summarize(t5[t5.day.isin(days)], days)[k] for k in ("trades", "avg_usd", "t_stat")}}
        r["matched_trades"] = int(len(both))
        r["matched_exit_reason_differs"] = int((both["reason_1m"] != both["reason_5m"]).sum())
        r["matched_usd_1m"] = round(float(both["usd_1m"].sum()), 1)
        r["matched_usd_5m"] = round(float(both["usd_5m"].sum()), 1)
        r["only_1m"] = int((mm["_merge"] == "left_only").sum())
        r["only_5m"] = int((mm["_merge"] == "right_only").sum())
        out[n] = r
    pathlib.Path("results/parity").mkdir(parents=True, exist_ok=True)
    pathlib.Path("results/parity/resolution.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
