"""Integrity audit, Stage 3: data and execution assumptions.

Checks (frozen B_fade_v1 / B_fade_v3, base costs, no parameter changes):
 A. DST transition sessions: first live minute and coverage.
 B. Stale-run filter: where removed minutes fall (hour of day, weekday).
 C. Entry/exit delays caused by missing minutes.
 D. Same-bar stop/target ambiguity: exits where the stop-first rule decided
    the outcome, and the optimistic (target-first) bound.
 E. Roll-gap days: trades on them.
 F. Cost break-even: average gross P&L per trade vs. round-trip cost.
 G. Snapshot (TOS) vs true exchange OHLC (CC0 Kaggle NQ 1-min, 2023-01-03 ..
    2025-12-10): range levels, trade matching and P&L decomposition.

Usage: python scripts/integrity_data_exec.py -> results/integrity/data_execution_audit.json
"""
import json
import pathlib

import numpy as np
import pandas as pd

from asiabt.data import build_grid, hhmm_to_offset, load_minutes
from asiabt.engine import Costs, Params, run
from asiabt.metrics import summarize

CFG = json.loads(pathlib.Path("config/strategies.json").read_text())["candidates"]
OUT = pathlib.Path("results/integrity")


def tgt_grid():
    t = pd.read_csv("data/raw/crosscheck/tgt_nq_1m.bin")
    t.index = pd.to_datetime(t["timestamp ET"], format="%m/%d/%Y %H:%M") - pd.Timedelta(minutes=1)
    t = t[~t.index.duplicated()][["open", "high", "low", "close"]]
    return build_grid(t)


def dst_sessions(g):
    out = []
    for y in range(2020, 2027):
        for m, wk in ((3, 2), (11, 1)):  # 2nd Sunday of March, 1st Sunday of November
            sundays = pd.date_range(f"{y}-{m:02d}-01", periods=14, freq="D")
            sun = [d for d in sundays if d.dayofweek == 6][wk - 1]
            td = sun + pd.Timedelta(days=1)  # Monday trading day starts Sunday 18:00
            if td in g.days:
                i = g.days.get_loc(td)
                first = int(np.argmax(np.isfinite(g.c[i])))
                out.append({"trading_day": str(td.date()), "transition": "spring" if m == 3 else "fall",
                            "first_live_offset_min": first, "coverage": round(float(g.coverage[i]), 3)})
    return out


def stale_profile():
    raw = pd.read_parquet("data/nq_tos_1m.parquet")
    kept = load_minutes("data/nq_tos_1m.parquet")
    removed = raw.index.difference(kept.index)
    r = pd.Series(1, index=removed)
    in_halt = (removed.hour == 17)
    weekend = removed.dayofweek == 5
    trading_window = ~in_halt & ~weekend
    by_hour = r[trading_window].groupby(removed[trading_window].hour).size()
    return {"removed_total": int(len(removed)), "in_17h_halt": int(in_halt.sum()), "saturday": int(weekend.sum()),
            "other": int(trading_window.sum()),
            "other_by_hour": {int(k): int(v) for k, v in by_hour.items()},
            "other_distinct_days": int(pd.Index(removed[trading_window].normalize()).nunique())}


def delays(tr):
    flat = hhmm_to_offset("11:00")
    entry_delay = tr["entry_off"] - (tr["sig_off"] + 1)
    t = tr[tr["reason"] == "time"]
    return {"trades": int(len(tr)), "entry_delayed": int((entry_delay > 0).sum()),
            "max_entry_delay_min": int(entry_delay.max()) if len(tr) else 0,
            "time_exits": int(len(t)), "time_exit_after_flat": int((t["exit_off"] > flat).sum()),
            "max_time_exit_delay_min": int((t["exit_off"] - flat).max()) if len(t) else 0}


def same_bar(g, tr, costs=Costs()):
    """Exits by stop where the same 1-minute bar also traded through the target."""
    thru = costs.limit_through_ticks * costs.tick
    rows = []
    for _, t in tr[tr["reason"] == "stop"].iterrows():
        i = g.days.get_loc(t["day"])
        j = int(t["exit_off"])
        if not np.isfinite(t["target"]):
            continue
        hit_tgt = (g.h[i, j] >= t["target"] + thru) if t["side"] > 0 else (g.l[i, j] <= t["target"] - thru)
        if hit_tgt:
            alt = t["side"] * (t["target"] - t["entry_px"]) * costs.point_value - costs.commission_rt
            rows.append({"day": str(t["day"].date()), "usd_stop_first": round(t["usd"], 1), "usd_target_first": round(alt, 1)})
    d = pd.DataFrame(rows)
    return {"stop_exits": int((tr["reason"] == "stop").sum()), "ambiguous_exits": int(len(d)),
            "usd_effect_if_target_first": round(float((d["usd_target_first"] - d["usd_stop_first"]).sum()), 1) if len(d) else 0.0,
            "cases": rows}


def snapshot_vs_true(g, gt, p):
    a, b = "2023-01-03", "2025-12-10"
    st = gt.subset((gt.days >= a) & (gt.days <= b))
    so = g.subset(g.days.isin(st.days))
    st = st.subset(st.days.isin(so.days))
    # Asian range levels (18:00-00:00) on identical days
    rs, re = hhmm_to_offset("18:00"), hhmm_to_offset("00:00")
    with np.errstate(all="ignore"):
        dh = np.nanmax(st.h[:, rs:re], 1) - np.nanmax(so.h[:, rs:re], 1)
        dl = np.nanmin(so.l[:, rs:re], 1) - np.nanmin(st.l[:, rs:re], 1)
    # tgt is back-adjusted: remove the per-day constant offset using the median close difference
    off = np.nanmedian(st.c - so.c, axis=1)
    dh, dl = dh - off, dl + off
    t_true, t_snap = run(st, p), run(so, p)
    key = ["day", "side", "entry_off"]
    m = t_snap.merge(t_true, on=key, how="outer", suffixes=("_snap", "_true"), indicator=True)
    both = m[m["_merge"] == "both"]
    res = {
        "days": int(len(so)),
        "range_high_true_minus_snap_pts": {"median": float(np.nanmedian(dh)), "p90": float(np.nanpercentile(dh, 90)),
                                           "p99": float(np.nanpercentile(dh, 99))},
        "range_low_snap_minus_true_pts": {"median": float(np.nanmedian(dl)), "p90": float(np.nanpercentile(dl, 90))},
        "snap": {k: summarize(t_snap, so.days)[k] for k in ("trades", "net_usd", "avg_usd", "t_stat")},
        "true": {k: summarize(t_true, st.days)[k] for k in ("trades", "net_usd", "avg_usd", "t_stat")},
        "matched_trades": int(len(both)),
        "matched_same_exit_reason": int((both["reason_snap"] == both["reason_true"]).sum()),
        "matched_usd_snap": round(float(both["usd_snap"].sum()), 1),
        "matched_usd_true": round(float(both["usd_true"].sum()), 1),
        "only_snap_trades": int((m["_merge"] == "left_only").sum()),
        "only_snap_usd": round(float(m.loc[m["_merge"] == "left_only", "usd_snap"].sum()), 1),
        "only_true_trades": int((m["_merge"] == "right_only").sum()),
        "only_true_usd": round(float(m.loc[m["_merge"] == "right_only", "usd_true"].sum()), 1),
        "matched_reason_changes": both.loc[both["reason_snap"] != both["reason_true"], ["reason_snap", "reason_true"]]
        .value_counts().rename("n").reset_index().to_dict(orient="records"),
    }
    return res


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    g = build_grid(load_minutes("data/nq_tos_1m.parquet"))
    gt = tgt_grid()
    res = {"A_dst_sessions": dst_sessions(g), "B_stale_filter": stale_profile()}
    for n in ("B_fade_v1", "B_fade_v3"):
        p = Params(**CFG[n])
        tr = run(g, p)
        gross = run(g, p, Costs(commission_rt=0.0, slip_ticks=0.0, limit_through_ticks=0.0))
        roll = g.daily["roll_gap"]
        res[n] = {
            "C_delays": delays(tr),
            "D_same_bar_stop_target": same_bar(g, tr),
            "E_trades_on_roll_gap_days": int(tr["day"].map(roll).fillna(False).sum()),
            "F_costs": {"avg_gross_usd": round(float(gross["usd"].mean()), 1), "avg_net_usd": round(float(tr["usd"].mean()), 1),
                        "avg_cost_usd": round(float(gross["usd"].mean() - tr["usd"].mean()), 1)},
            "G_snapshot_vs_true": snapshot_vs_true(g, gt, p),
        }
    (OUT / "data_execution_audit.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str)[:7000])


if __name__ == "__main__":
    main()
