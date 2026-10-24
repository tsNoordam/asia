"""Reproduce the four improvement cycles (docs/IMPROVEMENT_LOG.md).

Each hypothesis is evaluated on TRAIN, VAL and pooled TRAIN+VAL only.
Usage: python scripts/cycles.py  -> results/cycles.csv
"""
import json
import pathlib

import pandas as pd

from asiabt.engine import Params, run
from asiabt.metrics import summarize
from asiabt.research import load_grid, period

C = json.loads(pathlib.Path("config/strategies.json").read_text())["candidates"]


def evaluate(label, p, rows):
    g = load_grid()
    r = {"cycle_test": label}
    for per in ("train", "val", "trainval"):
        sub = period(g, per)
        s = summarize(run(sub, p), sub.days)
        r.update({f"{per}_n": s["trades"], f"{per}_avg": round(s["avg_usd"], 1), f"{per}_t": round(s["t_stat"], 2),
                  f"{per}_dd": round(s["max_dd_usd"])})
    rows.append(r)
    print(r, flush=True)


def main():
    rows = []
    v1, v2, v3 = (Params(**C[k]) for k in ("B_fade_v1", "B_fade_v2", "B_fade_v3"))
    evaluate("v1", v1, rows)
    for mx in (0.125, 0.15, 0.175, 0.2, 0.225, 0.25, 0.3):          # cycle 1, H1
        evaluate(f"c1 max_ext={mx}", v1.replace(fd_max_ext=mx), rows)
    for tf in ("with", "against"):                                 # cycle 1, H2
        evaluate(f"c1 trend={tf}", v1.replace(trend_filter=tf), rows)
    for be in ("mid", "0.5", "0.75", "1.0"):                        # cycle 2
        evaluate(f"c2 v2 breakeven={be}", v2.replace(be_trigger=be), rows)
    for mt in (2, 3):                                              # cycle 3
        evaluate(f"c3 v2 max_trades={mt}", v2.replace(max_trades=mt), rows)
    for tf in (3, 10, 15):
        evaluate(f"c3 v2 tf={tf}", v2.replace(tf=tf), rows)
    for mh in (15, 30, 60, 90, 120, 180):                           # cycle 4
        evaluate(f"c4 v3 max_hold={mh}", v3.replace(max_hold_min=mh), rows)
    pd.DataFrame(rows).to_csv("results/cycles.csv", index=False)


if __name__ == "__main__":
    main()
