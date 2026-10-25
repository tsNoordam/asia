"""Tests for the TradingView <-> Python trade-list comparator."""
import importlib.util
import pathlib

import pandas as pd

spec = importlib.util.spec_from_file_location(
    "parity_compare", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "parity_compare.py")
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


def _py(tmp_path):
    t = pd.DataFrame({
        "day": pd.to_datetime(["2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08"]),
        "side": [1, -1, 1, -1], "entry_off": [500, 600, 700, 800], "exit_off": [560, 700, 1020, 900],
        "entry_px": [100.0, 200.0, 300.0, 400.0], "exit_px": [110.0, 190.0, 305.0, 410.0],
        "reason": ["target", "target", "time", "stop"], "usd": [195.0, 195.0, 95.0, -205.0]})
    f = tmp_path / "py.csv"
    t.to_csv(f, index=False)
    return pc.py_trades(str(f))


def _tv_export(py, tmp_path, mutate=None):
    rows = []
    for k, (_, t) in enumerate(py.iterrows(), start=1):
        side = "long" if t["side"] > 0 else "short"
        sig = {"target": "Target", "stop": "Stop", "time": "Time exit"}[t["reason"]]
        rows.append({"Trade #": k, "Type": f"Exit {side}", "Signal": sig, "Date/Time": t["exit_ts"],
                     "Price USD": t["exit_px"], "Net P&L USD": t["usd"]})
        rows.append({"Trade #": k, "Type": f"Entry {side}", "Signal": "Fade", "Date/Time": t["entry_ts"],
                     "Price USD": t["entry_px"], "Net P&L USD": t["usd"]})
    df = pd.DataFrame(rows)
    if mutate:
        df = mutate(df)
    f = tmp_path / "tv.csv"
    df.to_csv(f, index=False)
    return pc.parse_tv(str(f))


def test_identical_lists_match_fully(tmp_path):
    py = _py(tmp_path)
    rep = pc.compare(_tv_export(py, tmp_path), py)
    assert rep["matched"] == 4 and rep["classes"] == {"identical": 4}
    assert not rep["only_py"] and not rep["only_tv"]


def test_classifies_adjustment_intrabar_and_missing(tmp_path):
    py = _py(tmp_path)

    def mutate(df):
        df = df.copy()
        t1 = df["Trade #"] == 1
        df.loc[t1, "Price USD"] += 50.0                                # back-adjusted chart
        df.loc[(df["Trade #"] == 2) & df["Type"].str.startswith("Exit"), "Signal"] = "Stop"
        return df[df["Trade #"] != 4]                                  # TV never took trade 4

    rep = pc.compare(_tv_export(py, tmp_path, mutate), py)
    assert rep["classes"].get("adjustment") == 1
    assert rep["classes"].get("intrabar_exit") == 1
    assert rep["classes"].get("identical") == 1
    assert len(rep["only_py"]) == 1
