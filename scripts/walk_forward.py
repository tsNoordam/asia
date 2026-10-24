"""Rolling walk-forward test of the *selection process*.

Every 6 months from 2022-01 to the end of the data, choose the config with the
highest t-stat (min 40 trades) over the trailing 24 months from a small,
pre-declared grid, then trade it unchanged for the next 6 months. The
concatenated test windows form a walk-forward out-of-sample record that never
uses future data for selection. Done for the fade (B) and breakout (A)
families so the two are compared on equal terms.

Usage: python scripts/walk_forward.py   -> results/walk_forward.json
"""
import itertools
import json
import pathlib

import pandas as pd

from asiabt.engine import Params, run
from asiabt.metrics import summarize
from asiabt.research import load_grid

FAMILIES = {
    "fade": (Params(mode="fade", range_end="00:00", flat_time="11:00", fd_target="opposite",
                    fd_stop_buffer_atr=0.05, direction="both", max_trades=2),
             {"fd_min_ext": [0.075, 0.1, 0.125], "fd_max_ext": [0.2, 0.25, 99.0],
              "tf": [5, 15], "entry_cutoff": ["05:00", "08:00", "11:00"]}),
    "breakout": (Params(mode="breakout", range_end="02:00", bo_stop="atr", bo_stop_atr=0.5),
                 {"bo_target_r": [0.0, 1.5], "tf": [5, 15], "entry_cutoff": ["05:00", "08:00"],
                  "flat_time": ["11:00", "16:00"], "direction": ["both", "long", "short"]}),
}


def main():
    g = load_grid()
    starts = pd.date_range("2022-01-01", g.days.max(), freq="6MS")
    out = {}
    for fam, (base, grid) in FAMILIES.items():
        combos = [base.replace(**dict(zip(grid, v))) for v in itertools.product(*grid.values())]
        test_trades, log = [], []
        for s in starts:
            e = s + pd.DateOffset(months=6)
            tr_mask = (g.days >= s - pd.DateOffset(months=24)) & (g.days < s)
            train = g.subset(tr_mask)
            best, best_t = None, -1e9
            for p in combos:
                st = summarize(run(train, p), train.days)
                if st["trades"] >= 40 and st["t_stat"] > best_t:
                    best, best_t = p, st["t_stat"]
            test = g.subset((g.days >= s) & (g.days < e))
            if best is None or len(test) == 0:
                continue
            tt = run(test, best)
            test_trades.append(tt)
            st = summarize(tt, test.days)
            log.append({"test_start": str(s.date()), "chosen": {k: getattr(best, k) for k in grid},
                        "train_t": round(best_t, 2), "test_trades": st["trades"],
                        "test_avg_usd": round(st["avg_usd"], 1) if st["trades"] else 0.0,
                        "test_net_usd": round(st["net_usd"], 0)})
            print(fam, log[-1], flush=True)
        allt = pd.concat(test_trades)
        days = g.days[(g.days >= starts[0])]
        summ = summarize(allt, days)
        out[fam] = {"windows": log, "summary": summ}
        print(fam, "WALK-FORWARD:", {k: summ[k] for k in ("trades", "net_usd", "avg_usd", "t_stat", "pf", "sharpe", "max_dd_usd")})
    pathlib.Path("results/walk_forward.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
