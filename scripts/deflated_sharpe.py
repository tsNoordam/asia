"""Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014) for the frozen fade
candidates on pooled TRAIN+VAL, i.e. the data on which they were selected.

DSR = Phi( (SR - E[max SR_N]) * sqrt(T - 1) / sqrt(1 - g3*SR + (g4 - 1)/4 * SR^2) )
with SR, g3 (skew), g4 (raw kurtosis) of DAILY P&L (non-annualised) and
E[max SR_N] = sqrt(V) * ((1 - gamma) * z(1 - 1/N) + gamma * z(1 - 1/(N e))).

V (variance of Sharpe ratios across trials) is measured on the 2,592-config
focused fade sweep (B2 grid) re-scored on pooled TRAIN+VAL. N (number of
INDEPENDENT trials) is unknown: ~7,000 configurations were evaluated but they
are highly correlated, so DSR is reported for N = 1, 10, 100, 1,000, 7,000.
No single N is "correct", and DSR does not remove selection bias completely
(it ignores e.g. choices made while designing the grid and the data snooping
of the previously inspected OOS period).

Usage: python scripts/deflated_sharpe.py -> results/integrity/deflated_sharpe.json
"""
import json
import math
import pathlib
from statistics import NormalDist

import numpy as np

from asiabt.engine import Params, run
from asiabt.metrics import daily_pnl
from asiabt.research import load_grid, period, sweep

N = NormalDist()
GAMMA = 0.5772156649


def expected_max_sr(v: float, n: int) -> float:
    if n <= 1:
        return 0.0
    return math.sqrt(v) * ((1 - GAMMA) * N.inv_cdf(1 - 1 / n) + GAMMA * N.inv_cdf(1 - 1 / (n * math.e)))


def dsr(sr: float, sr0: float, T: int, skew: float, kurt: float) -> float:
    den = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    return N.cdf((sr - sr0) * math.sqrt(T - 1) / math.sqrt(den))


def main():
    cfg = json.loads(pathlib.Path("config/strategies.json").read_text())["candidates"]
    trials = []
    for rs, re in [("18:00", "00:00"), ("18:00", "02:00")]:
        trials.append(sweep(Params(mode="fade", range_start=rs, range_end=re, fd_max_ext=99.0), {
            "entry_cutoff": ["05:00", "08:00", "11:00"], "flat_time": ["11:00", "16:00"], "tf": [5, 15],
            "fd_min_ext": [0.05, 0.075, 0.1, 0.125, 0.15, 0.2], "fd_target": ["mid", "opposite"],
            "fd_stop_buffer_atr": [0.05, 0.1, 0.15], "direction": ["long", "short", "both"]},
            periods=("trainval",)))
    import pandas as pd
    tr = pd.concat(trials, ignore_index=True)
    sr_trials = tr["trainval_sharpe"].dropna().to_numpy() / math.sqrt(252)  # daily units
    V = float(np.var(sr_trials, ddof=1))
    g = load_grid()
    tv = period(g, "trainval")
    out = {"trials_in_variance_estimate": int(len(sr_trials)), "var_daily_sr_across_trials": V,
           "sd_annualised_sr_across_trials": float(math.sqrt(V) * math.sqrt(252)), "strategies": {}}
    for n in ("B_fade_v1", "B_fade_v3"):
        d = daily_pnl(run(tv, Params(**cfg[n])), tv.days).to_numpy()
        sr = d.mean() / d.std(ddof=1)
        skew = float(((d - d.mean()) ** 3).mean() / d.std(ddof=0) ** 3)
        kurt = float(((d - d.mean()) ** 4).mean() / d.std(ddof=0) ** 4)
        res = {"T_days": len(d), "sr_daily": float(sr), "sr_annualised": float(sr * math.sqrt(252)),
               "skew": skew, "kurtosis": kurt, "psr_vs_0": dsr(sr, 0.0, len(d), skew, kurt), "dsr": {}}
        for k in (1, 10, 100, 1000, 7000):
            sr0 = expected_max_sr(V, k)
            res["dsr"][str(k)] = {"expected_max_sr_annualised": sr0 * math.sqrt(252),
                                  "dsr": dsr(sr, sr0, len(d), skew, kurt)}
        out["strategies"][n] = res
    p = pathlib.Path("results/integrity")
    p.mkdir(parents=True, exist_ok=True)
    (p / "deflated_sharpe.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
