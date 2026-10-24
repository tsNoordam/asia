"""Validate the primary TOS-derived NQ minute bars against independent data.

Writes results/data_validation.json and prints a summary. Checks:
1. Coverage, stale-run filtering, low-coverage days, roll-gap days.
2. Timezone/DST: minute closes vs. the independent CC0 Kaggle NQ 1-minute set
   (back-adjusted, labelled at bar END in ET) separately for EST and EDT months.
3. High/low understatement caused by 3-second snapshot sampling.
4. Hourly closes vs. Yahoo Finance NQ=F (front month, unadjusted).
"""
import json
import pathlib

import pandas as pd

from asiabt.data import build_grid, flag_roll_days, load_minutes

OUT = pathlib.Path("results")


def main():
    OUT.mkdir(exist_ok=True)
    res = {}
    raw = pd.read_parquet("data/nq_tos_1m.parquet")
    m = load_minutes("data/nq_tos_1m.parquet")
    g = build_grid(m)
    res["raw_minutes"] = len(raw)
    res["minutes_after_stale_filter"] = len(m)
    res["first_ts"], res["last_ts"] = str(m.index.min()), str(m.index.max())
    res["trading_days"] = len(g)
    res["days_coverage_lt_80pct"] = [d.strftime("%Y-%m-%d") for d in g.days[g.coverage < 0.8]]
    res["roll_gap_days"] = [d.strftime("%Y-%m-%d") for d in g.days[flag_roll_days(g).values]]

    t = pd.read_csv("data/raw/crosscheck/tgt_nq_1m.bin")
    t.index = pd.to_datetime(t["timestamp ET"], format="%m/%d/%Y %H:%M") - pd.Timedelta(minutes=1)
    t = t[~t.index.duplicated()]
    j = m[["open", "high", "low", "close"]].join(t[["open", "high", "low", "close"]], rsuffix="_t", how="inner")
    off = (j["close"] - j["close_t"]).groupby(j.index.to_period("D")).transform("median")
    r = j["close"] - j["close_t"] - off
    edt = j.index.month.isin([4, 5, 6, 7, 8, 9, 10])
    res["tgt_overlap_minutes"] = len(j)
    res["tgt_close_match_within_1pt"] = {
        "all": round(float((r.abs() <= 1).mean()), 4),
        "EDT_months": round(float((r[edt].abs() <= 1).mean()), 4),
        "EST_months": round(float((r[~edt].abs() <= 1).mean()), 4)}
    for lag in (-60, 60):  # a one-hour timezone error would show up here
        tt = t.copy()
        tt.index = tt.index + pd.Timedelta(minutes=lag)
        jj = m[["close"]].join(tt[["close"]], rsuffix="_t", how="inner")
        o2 = (jj["close"] - jj["close_t"]).groupby(jj.index.to_period("D")).transform("median")
        res[f"tgt_close_match_if_shifted_{lag}min"] = round(float(((jj["close"] - jj["close_t"] - o2).abs() <= 1).mean()), 4)
    hu = (j["high_t"] + off) - j["high"]
    lu = j["low"] - (j["low_t"] + off)
    res["minute_high_understatement_pts"] = {q: float(hu.quantile(p)) for q, p in
                                             [("p50", .5), ("p90", .9), ("p99", .99)]}
    res["minute_low_understatement_pts"] = {q: float(lu.quantile(p)) for q, p in
                                            [("p50", .5), ("p90", .9), ("p99", .99)]}

    y = pd.read_parquet("data/raw/crosscheck/yahoo_nqf_1h.parquet")
    y.index = y.index.tz_convert("America/New_York").tz_localize(None)
    # Yahoo labels hourly bars at their START; compare close of hour [h, h+1)
    mc = m["close"].resample("1h", label="left", closed="left").last()
    jj = pd.concat([mc.rename("tos"), y["close"].rename("yahoo")], axis=1, join="inner").dropna()
    d = jj["tos"] - jj["yahoo"]
    res["yahoo_overlap_hours"] = len(jj)
    res["yahoo_hourly_close_absdiff_pts"] = {"median": float(d.abs().median()),
                                             "p90": float(d.abs().quantile(.9)),
                                             "share_within_2pts": round(float((d.abs() <= 2).mean()), 4)}
    (OUT / "data_validation.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if not isinstance(v, list)}, indent=1))
    print("low coverage days:", len(res["days_coverage_lt_80pct"]), "roll gap days:", len(res["roll_gap_days"]))


if __name__ == "__main__":
    main()
