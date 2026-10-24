"""Phase 3/5 parameter sweeps for Candidate A (breakout) and B (fade).

Only TRAIN and VAL are evaluated (asiabt.research.sweep refuses OOS).
Long and short sides are swept separately, as required.
Outputs results/sweep_A.csv, sweep_B.csv and sweep_B2.csv (focused fade sweep).
Usage: python scripts/sweep_candidates.py [A] [B] [B2]
"""
import pathlib
import sys
import time

from asiabt.engine import Params
from asiabt.research import sweep

RANGES = [("18:00", "00:00"), ("18:00", "02:00"), ("20:00", "02:00")]


def run_A():
    rows = []
    for rs, re in RANGES:
        base = Params(mode="breakout", range_start=rs, range_end=re)
        rows.append(sweep(base, {
            "entry_cutoff": ["05:00", "08:00", "11:00"],
            "flat_time": ["11:00", "16:00"],
            "tf": [5, 15],
            "bo_buffer_atr": [0.0, 0.1],
            "bo_stop": ["opposite", "mid", "atr"],
            "bo_target_r": [0.0, 1.5, 3.0],
            "direction": ["long", "short"],
        }))
    return rows


def run_B():
    rows = []
    for rs, re in RANGES:
        base = Params(mode="fade", range_start=rs, range_end=re)
        rows.append(sweep(base, {
            "entry_cutoff": ["05:00", "08:00", "11:00"],
            "flat_time": ["11:00", "16:00"],
            "tf": [5, 15],
            "fd_min_ext": [0.0, 0.1, 0.25],
            "fd_max_ext": [0.5, 99.0],
            "fd_target": ["mid", "opposite", "r"],
            "fd_stop_buffer_atr": [0.05, 0.15],
            "direction": ["long", "short"],
        }))
    return rows


def run_B2():
    """Focused fade sweep around the plateau found in sweep B (TRAIN/VAL only)."""
    rows = []
    for rs, re in [("18:00", "00:00"), ("18:00", "02:00")]:
        base = Params(mode="fade", range_start=rs, range_end=re, fd_max_ext=99.0)
        rows.append(sweep(base, {
            "entry_cutoff": ["05:00", "08:00", "11:00"],
            "flat_time": ["11:00", "16:00"],
            "tf": [5, 15],
            "fd_min_ext": [0.05, 0.075, 0.1, 0.125, 0.15, 0.2],
            "fd_target": ["mid", "opposite"],
            "fd_stop_buffer_atr": [0.05, 0.1, 0.15],
            "direction": ["long", "short", "both"],
        }))
    return rows


def main():
    import pandas as pd
    pathlib.Path("results").mkdir(exist_ok=True)
    runners = {"A": run_A, "B": run_B, "B2": run_B2}
    for w in sys.argv[1:] or ["A", "B", "B2"]:
        t0 = time.time()
        df = pd.concat(runners[w](), ignore_index=True)
        df.to_csv(f"results/sweep_{w}.csv", index=False)
        print(w, len(df), "configs", f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
