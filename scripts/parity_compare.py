"""Python <-> TradingView (Pine) trade-list parity comparison.

Inputs
  --tv   CSV exported from TradingView Strategy Tester ("List of trades" ->
         Export). Two rows per trade (Entry / Exit). Column names vary between
         TradingView versions; they are matched case-insensitively:
         type ('Entry long', 'Exit short', ...), date/time, signal, price,
         P&L/profit. Times must be in America/New_York (set the chart timezone
         to New York before exporting) unless --tv-tz is given.
  --py   Python trade list (results/eval/trades_<name>.csv) produced with the
         SAME rules, costs and date range.

Matching: same NY trading day and side, entry times within --tol minutes.
Each matched pair is classified:
  identical         entry/exit within 1 tick, same exit time and reason
  adjustment        entry, stop and exit differ by the same constant (> 1 tick):
                    back-adjusted continuous contract on the chart
  resolution        same entry, exit time differs but within --tol minutes
  intrabar_exit     exit reason differs (e.g. stop vs target) -> intrabar path
                    assumption or chart resolution
  price_diff        any other price difference > 1 tick -> investigate
Unmatched trades are listed separately; they indicate data differences or an
implementation defect and must be reviewed manually.

Usage:
  python scripts/parity_compare.py --tv tv_trades.csv --py results/eval/trades_B_fade_v3r1.csv \
      [--start 2026-01-01 --end 2026-03-31] [--tol 5] [--out results/parity/report.json]
"""
from __future__ import annotations

import argparse
import json
import pathlib

import pandas as pd

TICK = 0.25


def _col(df, *keys):
    for c in df.columns:
        lc = c.lower()
        if all(k in lc for k in keys):
            return c
    raise KeyError(f"no column containing {keys} in {list(df.columns)}")


def parse_tv(path: str, tz: str = "America/New_York") -> pd.DataFrame:
    """Convert a TradingView 'List of trades' export to one row per trade."""
    raw = pd.read_csv(path)
    c_trade, c_type = _col(raw, "trade"), _col(raw, "type")
    c_time = next(c for c in raw.columns if "date" in c.lower() or "time" in c.lower())
    c_sig, c_px = _col(raw, "signal"), _col(raw, "price")
    try:
        c_pnl = _col(raw, "p&l")
    except KeyError:
        c_pnl = _col(raw, "profit")
    raw["ts"] = pd.to_datetime(raw[c_time])
    if tz != "America/New_York":
        raw["ts"] = raw["ts"].dt.tz_localize(tz).dt.tz_convert("America/New_York").dt.tz_localize(None)
    rows = []
    for tid, g in raw.groupby(c_trade):
        ent = g[g[c_type].str.lower().str.startswith("entry")]
        ext = g[g[c_type].str.lower().str.startswith("exit")]
        if ent.empty:
            continue
        e = ent.iloc[0]
        x = ext.iloc[0] if len(ext) else None
        side = 1 if "long" in e[c_type].lower() else -1
        rows.append({"tv_trade": tid, "side": side, "entry_ts": e["ts"], "entry_px": float(e[c_px]),
                     "exit_ts": x["ts"] if x is not None else pd.NaT,
                     "exit_px": float(x[c_px]) if x is not None else float("nan"),
                     "exit_signal": str(x[c_sig]) if x is not None else "open",
                     "usd": float(str(x[c_pnl]).replace(",", "")) if x is not None else float("nan")})
    return pd.DataFrame(rows)


def py_trades(path: str) -> pd.DataFrame:
    t = pd.read_csv(path, parse_dates=["day"])
    start = t["day"] - pd.Timedelta(hours=6)
    t["entry_ts"] = start + pd.to_timedelta(t["entry_off"], unit="min")
    t["exit_ts"] = start + pd.to_timedelta(t["exit_off"], unit="min")
    return t


def _reason_tv(sig: str) -> str:
    s = sig.lower()
    return "stop" if "stop" in s else "target" if "target" in s else "time" if "time" in s else s


def compare(tv: pd.DataFrame, py: pd.DataFrame, tol_min: int = 5) -> dict:
    tv = tv.copy()
    tv["day"] = (tv["entry_ts"] + pd.Timedelta(hours=6)).dt.normalize()
    pairs, used = [], set()
    for i, p in py.iterrows():
        cand = tv[(tv["day"] == p["day"]) & (tv["side"] == p["side"]) & (~tv.index.isin(used))]
        if cand.empty:
            continue
        dt = (cand["entry_ts"] - p["entry_ts"]).abs()
        j = dt.idxmin()
        if dt[j] <= pd.Timedelta(minutes=tol_min):
            used.add(j)
            pairs.append((i, j))
    rows = []
    for i, j in pairs:
        p, t = py.loc[i], tv.loc[j]
        d_entry, d_exit = t["entry_px"] - p["entry_px"], t["exit_px"] - p["exit_px"]
        reason_py = "stop" if str(p["reason"]).startswith("stop") else "target" if str(p["reason"]).startswith("target") else "time"
        reason_tv = _reason_tv(t["exit_signal"])
        same_time = t["exit_ts"] == p["exit_ts"]
        if abs(d_entry) <= TICK and abs(d_exit) <= TICK and same_time and reason_py == reason_tv:
            cls = "identical"
        elif reason_py != reason_tv:
            cls = "intrabar_exit"
        elif abs(d_entry) > TICK and abs(d_entry - d_exit) <= TICK:
            cls = "adjustment"
        elif abs(d_entry) <= TICK and not same_time and abs(t["exit_ts"] - p["exit_ts"]) <= pd.Timedelta(minutes=tol_min):
            cls = "resolution"
        else:
            cls = "price_diff"
        rows.append({"day": str(p["day"].date()), "side": int(p["side"]), "class": cls,
                     "entry_py": str(p["entry_ts"]), "entry_tv": str(t["entry_ts"]),
                     "d_entry_px": d_entry, "d_exit_px": d_exit, "reason_py": reason_py, "reason_tv": reason_tv,
                     "usd_py": float(p["usd"]), "usd_tv": float(t["usd"])})
    m = pd.DataFrame(rows)
    only_py = py.drop(index=[i for i, _ in pairs])
    only_tv = tv.drop(index=[j for _, j in pairs])
    return {
        "py_trades": int(len(py)), "tv_trades": int(len(tv)), "matched": int(len(m)),
        "classes": m["class"].value_counts().to_dict() if len(m) else {},
        "matched_usd_py": float(m["usd_py"].sum()) if len(m) else 0.0,
        "matched_usd_tv": float(m["usd_tv"].sum()) if len(m) else 0.0,
        "only_py": only_py[["day", "side", "entry_ts", "usd"]].astype(str).to_dict(orient="records"),
        "only_tv": only_tv[["day", "side", "entry_ts", "usd"]].astype(str).to_dict(orient="records"),
        "pairs": rows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tv", required=True)
    ap.add_argument("--py", required=True)
    ap.add_argument("--tv-tz", default="America/New_York")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--tol", type=int, default=5)
    ap.add_argument("--out", default="results/parity/report.json")
    a = ap.parse_args()
    tv, py = parse_tv(a.tv, a.tv_tz), py_trades(a.py)
    if a.start:
        tv, py = tv[tv["entry_ts"] >= a.start], py[py["day"] >= a.start]
    if a.end:
        tv, py = tv[tv["entry_ts"] <= pd.Timestamp(a.end) + pd.Timedelta(days=1)], py[py["day"] <= a.end]
    rep = compare(tv.reset_index(drop=True), py.reset_index(drop=True), a.tol)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps({k: v for k, v in rep.items() if k not in ("pairs", "only_py", "only_tv")}, indent=1))


if __name__ == "__main__":
    main()
