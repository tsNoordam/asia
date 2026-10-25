"""Before/after comparison of every reported headline metric.

BEFORE = results/baseline_50f822f (snapshot of commit 50f822f)
AFTER  = current results/ (regenerated with the corrected code)

Usage: python scripts/integrity_before_after.py -> results/integrity/before_after.csv
"""
import json
import pathlib

import pandas as pd

B = pathlib.Path("results/baseline_50f822f")
A = pathlib.Path("results")
KEYS = ["trades", "net_usd", "pf", "win_rate", "avg_usd", "t_stat", "sharpe", "max_dd_usd", "exposure"]


def main():
    b = pd.read_csv(B / "eval" / "summary.csv")
    a = pd.read_csv(A / "eval" / "summary.csv")
    m = b.merge(a, on=["strategy", "period"], how="left", suffixes=("_before", "_after"))
    rows = []
    for _, r in m.iterrows():
        for k in KEYS:
            x, y = r[f"{k}_before"], r[f"{k}_after"]
            if pd.isna(x) and pd.isna(y):
                continue
            if pd.isna(x) or pd.isna(y) or abs(float(x) - float(y)) > 1e-6 * max(1.0, abs(float(x))):
                rows.append({"source": "eval/summary.csv", "strategy": r["strategy"], "period": r["period"],
                             "metric": k, "before": x, "after": y})
    for name in ("walk_forward.json", "robustness.json"):
        bj, aj = json.loads((B / name).read_text()), json.loads((A / name).read_text())

        def walk(x, y, path):
            if isinstance(x, dict) and isinstance(y, dict):
                for k in x:
                    if k in y:
                        walk(x[k], y[k], path + [k])
            elif isinstance(x, (int, float)) and isinstance(y, (int, float)):
                if abs(x - y) > 1e-6 * max(1.0, abs(x)):
                    rows.append({"source": name, "strategy": "/".join(path[:2]), "period": "/".join(path[2:-1]),
                                 "metric": path[-1], "before": x, "after": y})

        walk(bj, aj, [])
    df = pd.DataFrame(rows)
    out = pathlib.Path("results/integrity")
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "before_after.csv", index=False)
    print(f"{len(df)} changed values")
    if len(df):
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()
