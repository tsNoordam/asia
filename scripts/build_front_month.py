"""Build the pre-2020 front-month NY-time minute series from Databento
per-contract bars using the pre-registered rules in asiabt.independent.

Usage: python scripts/build_front_month.py data/raw/databento/nq_ohlcv1m_2010-06-06_2019-12-31.parquet
       -> data/nq_exchange_pre2020_1m.parquet
"""
import sys

import pandas as pd

from asiabt.independent import fill_quiet_minutes, front_month


def main():
    bars = pd.read_parquet(sys.argv[1])
    if "ts_event" in bars.columns:
        bars = bars.set_index("ts_event")
    fm = fill_quiet_minutes(front_month(bars[["open", "high", "low", "close", "volume", "symbol"]]))
    fm.index.name = "ts_ny"
    fm.to_parquet("data/nq_exchange_pre2020_1m.parquet")
    print("saved", len(fm), fm.index.min(), fm.index.max(), fm["contract"].nunique(), "contracts")


if __name__ == "__main__":
    main()
