"""Reproduce the pooled TRAIN+VAL selection steps (Phase 3/5):

1. Candidate A representative: breakout grid evaluated on pooled TRAIN+VAL;
   pick the config whose worst neighbour (varying the buffer) is best.
2. Candidate B v1: fade plateau grid on pooled TRAIN+VAL; pick the config
   whose worst neighbour (varying the min excursion) is best.
3. Candidate C threshold: tercile edges of range/ATR on TRAIN.

Outputs results/select_A_pooled.csv, results/select_B_pooled.csv.
Usage: python scripts/select_v1.py
"""
import numpy as np

from asiabt.engine import Params
from asiabt.research import load_grid, period, sweep


def main():
    a = sweep(Params(mode="breakout", bo_stop_atr=0.5), {
        "range_end": ["00:00", "02:00"], "entry_cutoff": ["05:00", "08:00"], "flat_time": ["11:00", "16:00"],
        "tf": [5, 15], "bo_buffer_atr": [0.0, 0.1], "bo_stop": ["mid", "atr"], "bo_target_r": [0.0, 1.5],
        "direction": ["both", "long", "short"]}, periods=("trainval",))
    a["nb_min_t"] = a.groupby(["range_end", "entry_cutoff", "flat_time", "tf", "bo_stop", "bo_target_r",
                               "direction"])["trainval_t_stat"].transform("min")
    a.to_csv("results/select_A_pooled.csv", index=False)
    print(a.sort_values("nb_min_t", ascending=False).head(5)[
        ["range_end", "entry_cutoff", "flat_time", "tf", "bo_buffer_atr", "bo_stop", "bo_target_r", "direction",
         "trainval_trades", "trainval_avg_usd", "trainval_t_stat", "nb_min_t"]].round(2).to_string())

    b = sweep(Params(mode="fade", range_end="00:00", direction="both", fd_target="opposite"), {
        "entry_cutoff": ["05:00", "08:00", "11:00"], "flat_time": ["11:00", "16:00"], "tf": [5, 15],
        "fd_min_ext": [0.075, 0.1, 0.125], "fd_stop_buffer_atr": [0.05, 0.1]}, periods=("trainval",))
    b["nb_min_t"] = b.groupby(["entry_cutoff", "flat_time", "tf", "fd_stop_buffer_atr"])["trainval_t_stat"].transform("min")
    b.to_csv("results/select_B_pooled.csv", index=False)
    print(b.sort_values("nb_min_t", ascending=False).head(5)[
        ["entry_cutoff", "flat_time", "tf", "fd_min_ext", "fd_stop_buffer_atr", "trainval_trades",
         "trainval_avg_usd", "trainval_t_stat", "nb_min_t"]].round(2).to_string())

    tr = period(load_grid(), "train")
    ratios = [(np.nanmax(tr.h[i, :360]) - np.nanmin(tr.l[i, :360])) / tr.daily.atr14_prev.iat[i]
              for i in range(len(tr)) if tr.daily.atr14_prev.iat[i] > 0 and np.isfinite(tr.h[i, :360]).any()]
    print("hybrid threshold = lower tercile of TRAIN range/ATR:", np.round(np.nanquantile(ratios, [1 / 3, 2 / 3]), 3))


if __name__ == "__main__":
    main()
