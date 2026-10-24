"""Download independent NQ data sets used only to CROSS-CHECK the primary
TOS-derived minute bars (see docs/DATA.md).

1. Yahoo Finance `NQ=F` 1-hour bars (front-month, unadjusted, ~730 days).
2. Kaggle `tgtanalytics/nq-futures-1min-bar-2022-2025` (CC0) 1-minute NQ bars.
3. Hugging Face `lynx1231/historical-equity-index-futures-data-sample`
   per-contract NQ minute bars (evaluation sample, licence "other").

Outputs go to data/raw/crosscheck/.
"""
import pathlib

import requests
import yfinance as yf

OUT = pathlib.Path("data/raw/crosscheck")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    d = yf.download("NQ=F", interval="1h", period="730d", progress=False, auto_adjust=False)
    d.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in d.columns]
    d.to_parquet(OUT / "yahoo_nqf_1h.parquet")
    print("yahoo", len(d), d.index.min(), d.index.max())

    for url, name in [
        ("https://www.kaggle.com/api/v1/datasets/download/tgtanalytics/nq-futures-1min-bar-2022-2025/"
         "Dataset_NQ_1min_2022_2025.csv", "tgt_nq_1m.bin"),
        ("https://huggingface.co/datasets/lynx1231/historical-equity-index-futures-data-sample/"
         "resolve/main/data/minute/part-00000.parquet", "lynx_minute.parquet"),
    ]:
        r = requests.get(url, timeout=600)
        r.raise_for_status()
        (OUT / name).write_bytes(r.content)
        print(name, len(r.content))


if __name__ == "__main__":
    main()
