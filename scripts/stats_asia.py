"""Descriptive statistics of the Asian range (TRAIN+VAL only by default).

For each range definition: width vs ATR, how often the range is broken
before 08:00 / 11:00 NY, how often a broken side is re-entered (a 1-minute
close back inside the range after the first break), and how far the first
break extends (in range widths) before 11:00. Breaks are measured from
1-minute highs/lows after range_end.

Usage: python scripts/stats_asia.py [--periods train val]
"""
import argparse
import json
import pathlib

import numpy as np
import pandas as pd

from asiabt.data import hhmm_to_offset as off
from asiabt.research import load_grid, period

RANGES = {"R1 18:00-00:00": ("18:00", "00:00"), "R2 18:00-02:00": ("18:00", "02:00"),
          "R3 20:00-02:00": ("20:00", "02:00")}


def stats_for(g, rs, re):
    rows = []
    a, b = off(rs), off(re)
    t08, t11 = off("08:00"), off("11:00")
    for i in range(len(g)):
        h, l, c = g.h[i], g.l[i], g.c[i]
        atr = g.daily["atr14_prev"].iat[i]
        if np.isfinite(c[a:b]).mean() < 0.9 or np.isfinite(c[b:t11]).mean() < 0.8 or not atr > 0:
            continue
        RH, RL = np.nanmax(h[a:b]), np.nanmin(l[a:b])
        W = RH - RL
        hh, ll, cc = h[b:t11], l[b:t11], c[b:t11]
        up = np.where(hh > RH)[0]
        dn = np.where(ll < RL)[0]
        first_up = up[0] if len(up) else 10 ** 6
        first_dn = dn[0] if len(dn) else 10 ** 6
        n08 = t08 - b
        broke08 = min(first_up, first_dn) < n08
        broke11 = min(first_up, first_dn) < 10 ** 6
        side = 0 if not broke11 else (1 if first_up < first_dn else -1)
        reentry = both = np.nan
        ext = np.nan
        if side:
            k = first_up if side > 0 else first_dn
            after_c = cc[k:]
            inside = (after_c < RH) if side > 0 else (after_c > RL)
            reentry = float(np.nanmax(inside) if len(after_c) else 0)
            both = float(first_up < 10 ** 6 and first_dn < 10 ** 6)
            ext = ((np.nanmax(hh) - RH) if side > 0 else (RL - np.nanmin(ll))) / W
        close11 = cc[np.isfinite(cc)][-1] if np.isfinite(cc).any() else np.nan
        rows.append(dict(day=g.days[i], width_atr=W / atr, broke08=broke08, broke11=broke11, side=side,
                         reentry=reentry, both_sides=both, ext_first_side=ext,
                         close11_pos=(close11 - RL) / W))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--periods", nargs="+", default=["train", "val"])
    a = ap.parse_args()
    g = load_grid()
    parts = [period(g, p) for p in a.periods]
    out = {}
    for name, (rs, re) in RANGES.items():
        df = pd.concat([stats_for(sub, rs, re) for sub in parts])
        brk = df[df.side != 0]
        out[name] = {
            "sessions": len(df),
            "median_width_atr": round(df.width_atr.median(), 3),
            "break_before_08": round(df.broke08.mean(), 3),
            "break_before_11": round(df.broke11.mean(), 3),
            "first_break_up_share": round((brk.side > 0).mean(), 3),
            "reentry_after_first_break": round(brk.reentry.mean(), 3),
            "both_sides_broken_by_11": round(brk.both_sides.mean(), 3),
            "ext_first_side_median_widths": round(brk.ext_first_side.median(), 3),
            "ext_ge_1_width_share": round((brk.ext_first_side >= 1).mean(), 3),
            "close11_outside_on_first_break_side": round(
                ((brk.side > 0) & (brk.close11_pos > 1) | (brk.side < 0) & (brk.close11_pos < 0)).mean(), 3),
        }
    tag = "_".join(a.periods)
    pathlib.Path("results").mkdir(exist_ok=True)
    pathlib.Path(f"results/asia_stats_{tag}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
