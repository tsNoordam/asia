"""Download the public Kaggle dataset `brtnsmth/intraday-market-data` and
reduce the /NQ column to 1-minute OHLC bars.

Source: https://www.kaggle.com/datasets/brtnsmth/intraday-market-data
(ThinkOrSwim snapshots of /NQ, /ES and other symbols roughly every 3 seconds,
timestamps in America/New_York, Feb-2020 onward, one CSV per week.)

Important properties (see docs/DATA.md):
* /NQ is TOS's front-month continuous symbol: UNADJUSTED, so a price jump
  equal to the calendar spread appears on roll days.
* Prices are *snapshots* of the last trade, not every trade. 1-minute highs
  and lows built from ~20 snapshots understate the true extremes slightly.
* No /NQ volume column exists, so no volume-based filters can use this data.

The whole dataset is downloaded once as a zip (~0.8 GB; single-file downloads
of files inside sub-folders return 404 on the anonymous API), every weekly CSV
is reduced in memory to minute bars (open, high, low, close, n_snapshots) and
the result is written to data/nq_tos_1m.parquet.

Usage:  python scripts/fetch_tos_kaggle.py [--col /ES --out data/es_tos_1m.parquet]
"""
import argparse
import io
import pathlib
import zipfile

import pandas as pd
import requests

DS = "brtnsmth/intraday-market-data"
API = "https://www.kaggle.com/api/v1/datasets"


ZIP_URL = f"{API}/download/{DS}"


def to_minutes(raw: bytes, col="/NQ") -> pd.DataFrame:
    head = pd.read_csv(io.BytesIO(raw), nrows=0, encoding="utf-8-sig").columns
    if col not in head:
        return pd.DataFrame()
    df = pd.read_csv(io.BytesIO(raw), usecols=["TimeStamp", col], encoding="utf-8-sig")
    df["TimeStamp"] = pd.to_datetime(df["TimeStamp"], errors="coerce", format="mixed")
    df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna()
    df = df[df[col] > 0].set_index("TimeStamp").sort_index()
    g = df[col].resample("1min", label="left", closed="left")
    out = pd.DataFrame({"open": g.first(), "high": g.max(), "low": g.min(),
                        "close": g.last(), "n": g.count()})
    return out[out["n"] > 0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default="data/raw/tos_dataset.zip")
    ap.add_argument("--out", default="data/nq_tos_1m.parquet")
    ap.add_argument("--col", default="/NQ", help="symbol column, e.g. /NQ or /ES")
    a = ap.parse_args()
    zp = pathlib.Path(a.zip)
    if not zp.exists():
        zp.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(ZIP_URL, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(zp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
    parts = []
    with zipfile.ZipFile(zp) as z:
        names = sorted(n for n in z.namelist() if "week ending" in n)
        for n in names:
            bars = to_minutes(z.read(n), a.col)
            print(n, len(bars), flush=True)
            if len(bars):
                parts.append(bars)
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]  # the newest week is stored twice
    df.index.name = "ts_ny"  # naive America/New_York wall-clock time
    df.to_parquet(a.out)
    print("saved", a.out, len(df), df.index.min(), df.index.max())


if __name__ == "__main__":
    main()
