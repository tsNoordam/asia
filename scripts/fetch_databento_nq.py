"""PLAN / TOOLING ONLY — not executed in this project (no API key, no approval).

Fetch pre-2020 CME NQ 1-minute OHLCV from Databento (dataset GLBX.MDP3,
available from 2010-06-06) for the pre-registered independent test of the
frozen fade rules (docs/AUDIT.md §8, docs/PREREGISTRATION.md).

Safety:
* Requires DATABENTO_API_KEY in the environment.
* Always prints the cost quote from `metadata.get_cost` first and exits
  unless --approve-cost-usd is given and the quote does not exceed it.
* Refuses any end date after 2019-12-31 so the independent sample cannot
  overlap the 2020+ research data.

Data written:
  data/raw/databento/nq_ohlcv1m_<start>_<end>.parquet   all NQ outright contracts (parent symbology)
  data/raw/databento/nq_definitions.parquet             instrument definitions (expirations)
Then build the front-month series with scripts/build_front_month.py.

Usage (after approval):
  python scripts/fetch_databento_nq.py --start 2010-06-06 --end 2019-12-31            # quote only
  python scripts/fetch_databento_nq.py --start 2010-06-06 --end 2019-12-31 --approve-cost-usd 25
"""
import argparse
import os
import pathlib
import sys

DATASET = "GLBX.MDP3"
LAST_ALLOWED_END = "2019-12-31"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-06-06")
    ap.add_argument("--end", default=LAST_ALLOWED_END)
    ap.add_argument("--approve-cost-usd", type=float, default=None)
    ap.add_argument("--out", default="data/raw/databento")
    a = ap.parse_args()
    if a.end > LAST_ALLOWED_END:
        sys.exit(f"end {a.end} > {LAST_ALLOWED_END}: the independent sample must not overlap 2020+ data")
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        sys.exit("DATABENTO_API_KEY not set (no request made)")
    import databento as db  # pip install databento

    client = db.Historical(key)
    req = dict(dataset=DATASET, symbols=["NQ.FUT"], stype_in="parent", start=a.start, end=a.end)
    quote = client.metadata.get_cost(schema="ohlcv-1m", **req) + client.metadata.get_cost(schema="definition", **req)
    print(f"Databento cost quote for ohlcv-1m + definition {a.start}..{a.end}: ${quote:.2f}")
    if a.approve_cost_usd is None or quote > a.approve_cost_usd:
        sys.exit("not approved: re-run with --approve-cost-usd >= quote after the user approves the spend")
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    bars = client.timeseries.get_range(schema="ohlcv-1m", **req).to_df()
    bars.to_parquet(out / f"nq_ohlcv1m_{a.start}_{a.end}.parquet")
    defs = client.timeseries.get_range(schema="definition", **req).to_df()
    defs.to_parquet(out / "nq_definitions.parquet")
    print("saved", len(bars), "bars and", len(defs), "definitions")


if __name__ == "__main__":
    main()
