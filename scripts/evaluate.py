"""Full evaluation of frozen strategies from config/strategies.json.

For every requested strategy: metrics on TRAIN / VAL / OOS / FULL, long vs
short, by year, cost stress (gross, base, 2-tick + $7), MNQ economics, and
one-step parameter sensitivity. Writes results/eval/<name>.json and appends a
row per period to results/eval/summary.csv.

Usage:
  python scripts/evaluate.py                      # every baseline + candidate
  python scripts/evaluate.py B_fade_v1 B1_simple_breakout
  python scripts/evaluate.py --no-oos B_fade_v2   # development: hide OOS, writes results/eval_dev/
"""
import argparse
import dataclasses
import json
import pathlib

import pandas as pd

from asiabt.engine import Costs, Params, run
from asiabt.metrics import by_year, inference, summarize
from asiabt.research import load_grid, period

CFG = pathlib.Path("config/strategies.json")
OUT = pathlib.Path("results/eval")
COSTS = {
    "gross": Costs(commission_rt=0.0, slip_ticks=0.0, limit_through_ticks=0.0),
    "base": Costs(),
    "stress": Costs(commission_rt=7.0, slip_ticks=2.0),
    "mnq_base": Costs(point_value=2.0, commission_rt=1.30),
}
# one-step perturbations used for the sensitivity table
SENS = {
    "fade": {"fd_min_ext": (0.075, 0.125), "fd_stop_buffer_atr": (0.0, 0.1), "tf": (3, 15),
             "entry_cutoff": ("05:00", "11:00"), "flat_time": ("10:00", "12:00"),
             "range_end": ("23:00", "01:00")},
    "breakout": {"bo_stop_atr": (0.35, 0.75), "bo_target_r": (1.0, 2.0), "tf": (5, 30),
                 "entry_cutoff": ("05:00", "09:00"), "range_end": ("01:00", "03:00")},
}


def load_cfg():
    cfg = json.loads(CFG.read_text())
    out = {}
    for sect in ("baselines", "candidates"):
        out.update({k: v for k, v in cfg[sect].items()})
    return out


def params_of(spec):
    return None if spec is None else Params(**spec)


def _period_trades(trades, g, name):
    sub = period(g, name) if name != "full" else g
    return (trades[trades["day"].isin(sub.days)] if len(trades) else trades), sub.days


def split_stats(trades, g, periods):
    res = {}
    for name in periods:
        t, days = _period_trades(trades, g, name)
        res[name] = summarize(t, days)
    return res


def evaluate(name, spec, periods):
    g = load_grid()
    p = params_of(spec)
    if p is None:  # no-trade baseline
        empty = pd.DataFrame(columns=["day", "usd", "pts", "side", "hold_min"])
        return {"name": name, "params": None, "base": split_stats(empty, g, periods)}
    rep = {"name": name, "params": dataclasses.asdict(p)}
    trades = {}
    for cname, c in COSTS.items():
        trades[cname] = run(g, p, c)
        rep[cname] = split_stats(trades[cname], g, periods)
    t = trades["base"]
    # daily-level inference (day-block bootstrap, Newey-West); see asiabt.metrics.inference
    rep["inference"] = {per: inference(*_period_trades(t, g, per)) for per in periods}
    rep["by_year"] = by_year(t).round(2).reset_index().to_dict(orient="records")
    rep["by_side"] = {}
    for side, lab in ((1, "long"), (-1, "short")):
        rep["by_side"][lab] = split_stats(t[t["side"] == side], g, periods)
    rep["exit_reasons"] = t["reason"].value_counts().to_dict()
    # sensitivity: one parameter at a time, other parameters fixed
    sens = []
    for key, vals in SENS.get(p.mode, {}).items():
        for v in vals:
            q = p.replace(**{key: v})
            try:
                tq = run(g, q, COSTS["base"])
            except AssertionError:
                continue
            st = split_stats(tq, g, periods)
            sens.append({"param": key, "value": v,
                         **{f"{per}_{m}": st[per][m] for per in periods for m in ("trades", "avg_usd", "t_stat")}})
    rep["sensitivity"] = sens
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT / f"trades_{name}.csv", index=False)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--no-oos", action="store_true")
    a = ap.parse_args()
    cfg = load_cfg()
    names = a.names or list(cfg)
    periods = ["train", "val"] + ([] if a.no_oos else ["oos", "full"])
    global OUT
    if a.no_oos:  # development runs never overwrite the frozen full reports
        OUT = OUT.parent / "eval_dev"
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for n in names:
        rep = evaluate(n, cfg[n], periods)
        (OUT / f"{n}.json").write_text(json.dumps(rep, indent=1, default=str))
        for per in periods:
            s = rep["base"][per]
            rows.append({"strategy": n, "period": per, **{k: s.get(k) for k in (
                "trades", "net_usd", "pf", "win_rate", "avg_usd", "avg_win", "avg_loss", "t_stat",
                "sharpe", "max_dd_usd", "exposure", "long_n", "long_usd", "short_n", "short_usd")},
                **{k: rep.get("inference", {}).get(per, {}).get(k) for k in (
                    "daily_mean_usd", "daily_t_nw", "daily_mean_ci95", "trade_mean_ci95", "p_boot_le0", "block_len")}})
        b = rep["base"]
        print(f"{n:24s} " + " | ".join(
            f"{per}: n={b[per]['trades']} avg=${b[per]['avg_usd'] if b[per]['trades'] else 0:.0f} "
            f"t={b[per].get('t_stat', float('nan')):.2f}" for per in periods), flush=True)
    df = pd.DataFrame(rows)
    f = OUT / "summary.csv"
    if f.exists():
        old = pd.read_csv(f)
        df = pd.concat([old[~old["strategy"].isin(names)], df])
    df.to_csv(f, index=False)


if __name__ == "__main__":
    main()
