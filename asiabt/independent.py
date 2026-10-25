"""Conversion of exchange per-contract 1-minute bars (e.g. Databento GLBX.MDP3
ohlcv-1m, parent symbology) into the front-month, America/New_York minute
series used by asiabt. Rules are fixed BEFORE any pre-2020 data is seen
(docs/PREREGISTRATION.md):

* Outright contracts only (symbols without a spread separator).
* Front month for trading day D = the contract with the largest total volume
  on trading day D-1 (previous day only -> no look-ahead). The first day uses
  the nearest expiry present.
* Exchange trade bars exist only for minutes with trades. Gaps of at most
  `max_fill` minutes inside a trading day are filled with flat bars at the
  previous close (no trades = no price change). Longer gaps (halts, holidays,
  outages) stay missing and are handled by the engine's coverage rules.
* Prices are unadjusted; asiabt.data handles roll gaps in daily features.
"""
from __future__ import annotations

import pandas as pd

from .data import MINUTES_PER_DAY


def to_ny_naive(ts: pd.Series | pd.DatetimeIndex) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(ts)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    return idx.tz_convert("America/New_York").tz_localize(None)


def front_month(bars: pd.DataFrame, symbol_col: str = "symbol") -> pd.DataFrame:
    """bars: index = bar-open time (UTC or tz-aware), columns open, high, low,
    close, volume, `symbol_col`. Returns NY-naive front-month bars with a
    `contract` column."""
    b = bars[~bars[symbol_col].astype(str).str.contains("-")].copy()
    b.index = to_ny_naive(b.index)
    b["td"] = (b.index + pd.Timedelta(hours=6)).normalize()
    vol = b.groupby(["td", symbol_col])["volume"].sum().unstack(fill_value=0)
    days = vol.index
    choice = vol.idxmax(axis=1).shift(1)  # previous day's most active contract
    choice.iloc[0] = vol.columns[vol.iloc[0].to_numpy().nonzero()[0][0]] if vol.iloc[0].sum() else vol.columns[0]
    choice = choice.reindex(days)
    pick = b[symbol_col].to_numpy() == choice.reindex(b["td"]).to_numpy()
    out = b[pick].drop(columns=["td"]).rename(columns={symbol_col: "contract"}).sort_index()
    return out[~out.index.duplicated(keep="first")]


def fill_quiet_minutes(m: pd.DataFrame, max_fill: int = 30) -> pd.DataFrame:
    """Insert flat bars for gaps of <= max_fill minutes within a trading day."""
    td = (m.index + pd.Timedelta(hours=6)).normalize()
    parts = []
    for _, g in m.groupby(td):
        full = pd.date_range(g.index.min(), g.index.max(), freq="1min")
        r = g.reindex(full)
        missing = r["close"].isna()
        run_id = (~missing).cumsum()
        run_len = missing.groupby(run_id).transform("sum")
        fill = missing & (run_len <= max_fill)
        prev_close = r["close"].ffill()
        for c in ("open", "high", "low", "close"):
            r.loc[fill, c] = prev_close[fill]
        if "volume" in r:
            r.loc[fill, "volume"] = 0
        if "contract" in r:
            r["contract"] = r["contract"].ffill()
        parts.append(r[r["close"].notna()])
    out = pd.concat(parts)
    off = ((out.index.hour - 18) % 24) * 60 + out.index.minute
    return out[off < MINUTES_PER_DAY]
