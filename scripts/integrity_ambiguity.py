"""Integrity audit, Stage 2: frequency and effect of two-sided ambiguous fade
signals (both the upper and lower excursion qualify at one signal close).

For every frozen fade-using strategy, the three policies are run unchanged
otherwise: legacy_short_first (frozen behaviour), latest (chronological
1-minute rule, skip same-minute), skip. This is a MEASUREMENT of an
implementation defect, not a parameter search: the corrected policy was fixed
(see docs/AUDIT.md) before these numbers were produced.

Usage: python scripts/integrity_ambiguity.py -> results/integrity/ambiguity.csv
"""
import json
import pathlib

import pandas as pd

from asiabt.engine import Params, run
from asiabt.metrics import summarize
from asiabt.research import load_grid, period

C = json.loads(pathlib.Path("config/strategies.json").read_text())
NAMES = ["B2_simple_fade", "B_fade_v1", "B_fade_v2", "B_fade_v3", "C_hybrid_v1"]


def main():
    g = load_grid()
    cfg = {**C["baselines"], **C["candidates"]}
    rows = []
    for n in NAMES:
        for pol in ("legacy_short_first", "latest", "skip"):
            p = Params(**{**cfg[n], "fd_both_sides": pol})
            tr = run(g, p)
            for per in ("train", "val", "oos", "full"):
                sub = g if per == "full" else period(g, per)
                t = tr[tr["day"].isin(sub.days)]
                s = summarize(t, sub.days)
                amb = t[t["ambiguous"]]
                rows.append({"strategy": n, "policy": pol, "period": per, "trades": s["trades"],
                             "ambiguous_trades": len(amb), "ambiguous_short": int((amb["side"] < 0).sum()),
                             "ambiguous_long": int((amb["side"] > 0).sum()),
                             "ambiguous_usd": round(float(amb["usd"].sum()), 1),
                             "net_usd": round(s["net_usd"], 1), "avg_usd": round(s.get("avg_usd", 0) or 0, 1),
                             "t_stat": round(s.get("t_stat", float("nan")), 3),
                             "max_dd_usd": round(s["max_dd_usd"], 1)})
    df = pd.DataFrame(rows)
    out = pathlib.Path("results/integrity")
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "ambiguity.csv", index=False)
    print(df[df.period == "full"].to_string(index=False))


if __name__ == "__main__":
    main()
