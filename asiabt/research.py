"""Chronological splits and parameter-sweep helpers.

Splits (fixed BEFORE any candidate was tuned):
  TRAIN  2020-01-27 .. 2022-12-31  development (COVID crash, 2021 bull, 2022 bear)
  VAL    2023-01-01 .. 2024-06-30  parameter selection / model choice
  OOS    2024-07-01 .. 2026-10-23  PREVIOUSLY INSPECTED out-of-sample period
                                    ("OOS-I"). It was not used to choose parameters,
                                    but its results were viewed at v1 and after
                                    each improvement cycle (and full-sample baseline
                                    smoke tests were run before the split was fixed),
                                    so it is no longer a pristine holdout. Do not use
                                    it to select parameters, filters or strategies.
"""
from __future__ import annotations

import concurrent.futures as cf
import itertools
import os

import pandas as pd

from .data import DayGrid, build_grid, load_minutes
from .engine import Costs, Params, run
from .metrics import summarize

SPLITS = {
    "train": ("2020-01-01", "2022-12-31"),
    "val": ("2023-01-01", "2024-06-30"),
    "oos": ("2024-07-01", "2026-12-31"),
}

_GRID: DayGrid | None = None


def load_grid(path: str = "data/nq_tos_1m.parquet") -> DayGrid:
    global _GRID
    if _GRID is None:
        _GRID = build_grid(load_minutes(path))
    return _GRID


# Pooled TRAIN+VAL, used for model selection (never includes OOS).
POOLED = {"trainval": ("2020-01-01", "2024-06-30")}


def period(g: DayGrid, name: str) -> DayGrid:
    a, b = SPLITS[name] if name in SPLITS else POOLED[name]
    return g.subset((g.days >= a) & (g.days <= b))


def evaluate(p: Params, periods=("train", "val"), costs: Costs = Costs()) -> dict:
    g = load_grid()
    out = {}
    for name in periods:
        sub = period(g, name)
        out[name] = summarize(run(sub, p, costs), sub.days)
    return out


def _eval_row(args):
    p, periods, costs = args
    res = evaluate(p, periods, costs)
    row = {k: v for k, v in p.__dict__.items()}
    for per, s in res.items():
        for k in ("trades", "net_usd", "pf", "win_rate", "avg_usd", "t_stat", "sharpe", "max_dd_usd"):
            row[f"{per}_{k}"] = s[k]
    return row


def sweep(base: Params, grid: dict, periods=("train", "val"), costs: Costs = Costs(),
          workers: int | None = None) -> pd.DataFrame:
    """Cartesian sweep. OOS is deliberately not allowed here."""
    assert "oos" not in periods, "parameter sweeps must never touch the OOS period"
    keys = list(grid)
    combos = [base.replace(**dict(zip(keys, vals))) for vals in itertools.product(*grid.values())]
    combos = [p for p in combos if _valid(p)]
    load_grid()  # load once in the parent; forked workers inherit it
    with cf.ProcessPoolExecutor(workers or os.cpu_count()) as ex:
        rows = list(ex.map(_eval_row, [(p, periods, costs) for p in combos], chunksize=4))
    return pd.DataFrame(rows)


def _valid(p: Params) -> bool:
    from .data import hhmm_to_offset as off
    return off(p.range_start) < off(p.range_end) <= off(p.entry_cutoff) <= off(p.flat_time)
