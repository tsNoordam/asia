"""Robustness checks for the final candidate (and v1 for comparison).

1. Independent data: the same rules on the CC0 Kaggle NQ 1-minute set with
   true exchange highs/lows (2023-01 .. 2025-12), against the TOS-derived bars
   on the identical days.
2. Out-of-market: identical rules (ATR-scaled) on /ES from the same recorder,
   with ES contract economics ($50/pt).
3. Asian-session definitions R1/R2/R3 for the final candidate.
4. Bootstrap 95% confidence intervals of the mean trade per period:
   (a) i.i.d. resampling of individual TRADES (assumes independent trades;
       kept for comparability with the 50f822f report), and
   (b) circular block bootstrap over TRADING DAYS (asiabt.metrics.inference),
       which keeps same-session trades together and allows for serial
       dependence. (b) is the primary interval.

Usage: python scripts/robustness.py [strategy ...]  -> results/robustness.json
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd

from asiabt.data import build_grid, load_minutes
from asiabt.engine import Costs, Params, run
from asiabt.metrics import inference, summarize
from asiabt.research import SPLITS, load_grid, period

CFG = json.loads(pathlib.Path("config/strategies.json").read_text())["candidates"]


def tgt_grid():
    t = pd.read_csv("data/raw/crosscheck/tgt_nq_1m.bin")
    # labelled at bar END -> shift to bar start, like every other series here
    t.index = pd.to_datetime(t["timestamp ET"], format="%m/%d/%Y %H:%M") - pd.Timedelta(minutes=1)
    t = t[~t.index.duplicated()][["open", "high", "low", "close"]]
    return build_grid(t)


def boot_ci(x, n=5000, seed=7):
    x = np.asarray(x, float)
    if len(x) < 5:
        return [float("nan")] * 2
    rng = np.random.default_rng(seed)
    means = rng.choice(x, (n, len(x))).mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def compact(s):
    return {k: (round(s[k], 3) if isinstance(s[k], float) else s[k])
            for k in ("trades", "net_usd", "avg_usd", "t_stat", "pf", "win_rate", "sharpe", "max_dd_usd")}


def main():
    names = sys.argv[1:] or ["B_fade_v3", "B_fade_v1"]
    g = load_grid()
    gt = tgt_grid()
    es = build_grid(load_minutes("data/es_tos_1m.parquet"))
    es_costs = Costs(point_value=50.0, commission_rt=5.0)
    out = {}
    for n in names:
        p = Params(**CFG[n])
        r = {}
        # 1. independent data on the overlapping days (skip the ragged ends)
        a, b = "2023-01-03", "2025-12-10"
        sub_t = gt.subset((gt.days >= a) & (gt.days <= b))
        sub_o = g.subset(g.days.isin(sub_t.days))
        sub_t = sub_t.subset(sub_t.days.isin(sub_o.days))
        r["independent_data_tgt_2023_2025"] = compact(summarize(run(sub_t, p), sub_t.days))
        r["tos_same_days_2023_2025"] = compact(summarize(run(sub_o, p), sub_o.days))
        # 2. out-of-market /ES
        r["ES"] = {per: compact(summarize(run(period(es, per), p, es_costs), period(es, per).days))
                   for per in ("train", "val", "oos")}
        # 3. session definitions
        r["sessions"] = {}
        for lab, (rs, re) in {"R1 18-00": ("18:00", "00:00"), "R2 18-02": ("18:00", "02:00"),
                              "R3 20-02": ("20:00", "02:00")}.items():
            q = p.replace(range_start=rs, range_end=re,
                          entry_cutoff=max(p.entry_cutoff, re, key=lambda x: (int(x[:2]) - 18) % 24))
            r["sessions"][lab] = {per: compact(summarize(run(period(g, per), q), period(g, per).days))
                                  for per in ("train", "val", "oos")}
        # 4. bootstrap CI of mean trade
        r["bootstrap_mean_usd_ci95"] = {per: boot_ci(run(period(g, per), p)["usd"]) for per in SPLITS}
        r["bootstrap_mean_usd_ci95_label"] = "i.i.d. trade resampling (assumes independent trades)"
        r["day_block_inference"] = {per: inference(run(period(g, per), p), period(g, per).days) for per in SPLITS}
        out[n] = r
        print(n, json.dumps(r, indent=1))
    pathlib.Path("results/robustness.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
