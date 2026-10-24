"""Loading, validating and reshaping 1-minute NQ bars.

Conventions
-----------
* All timestamps are naive America/New_York wall-clock times. Session
  windows are defined in NY wall-clock time, so daylight-saving changes are
  handled by construction (18:00 NY is always 18:00 NY, whatever the UTC
  offset).
* A CME Globex *trading day* D runs from 18:00 NY on the previous calendar day
  to 17:00 NY on D (daily maintenance halt 17:00-18:00). Bars are therefore
  labelled with trading_day = calendar date of (timestamp + 6 hours).
* Each trading day is reshaped into a fixed grid of 1,380 one-minute slots
  (offset 0 = 18:00, offset 1379 = 16:59). Missing minutes are NaN.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import numpy as np
import pandas as pd

MINUTES_PER_DAY = 23 * 60  # 18:00 -> 17:00
DAY_START = dt.time(18, 0)


def hhmm_to_offset(hhmm: str) -> int:
    """'18:00' -> 0, '00:00' -> 360, '02:00' -> 480, '09:30' -> 930 ..."""
    h, m = map(int, hhmm.split(":"))
    return ((h - 18) % 24) * 60 + m


def offset_to_hhmm(off: int) -> str:
    t = (18 * 60 + off) % (24 * 60)
    return f"{t // 60:02d}:{t % 60:02d}"


def load_minutes(path: str, stale_run: int = 10) -> pd.DataFrame:
    """Load minute bars. With `stale_run` > 0, runs of at least that many
    consecutive minutes without any price change (o=h=l=c=previous close) are
    dropped: the TOS recorder keeps writing the last price while the market is
    closed (17:00 halt, holidays, early closes), which would otherwise look
    like real but motionless bars."""
    df = pd.read_parquet(path)
    df.index = pd.DatetimeIndex(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("America/New_York").tz_localize(None)
    df = df.sort_index()
    if stale_run > 0:
        flat = ((df["high"] == df["low"]) & (df["close"] == df["close"].shift(1))).to_numpy()
        # length of the run of consecutive flat minutes each minute belongs to
        grp = np.cumsum(~flat)
        run_len = pd.Series(flat.astype(int)).groupby(grp).transform("sum").to_numpy()
        # include the first bar of a run (it can differ from its predecessor but
        # is the start of a stale stretch only if followed by a long flat run)
        df = df[~(flat & (run_len >= stale_run))]
    return df


@dataclasses.dataclass
class DayGrid:
    """Trading days x minutes matrices."""
    days: pd.DatetimeIndex          # trading-day dates
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    coverage: np.ndarray            # fraction of minutes present per day
    daily: pd.DataFrame             # per-day OHLC + features (all lagged where needed)

    def __len__(self):
        return len(self.days)

    def subset(self, mask) -> "DayGrid":
        mask = np.asarray(mask)
        return DayGrid(self.days[mask], self.o[mask], self.h[mask], self.l[mask],
                       self.c[mask], self.coverage[mask], self.daily.loc[mask].copy())


def build_grid(m: pd.DataFrame, min_coverage: float = 0.0) -> DayGrid:
    ts = m.index
    td = (ts + pd.Timedelta(hours=6)).normalize()
    off = ((ts.hour - 18) % 24) * 60 + ts.minute
    keep = off < MINUTES_PER_DAY  # drops anything stamped inside the 17:00-18:00 halt
    m, td, off = m[keep], td[keep], np.asarray(off[keep])
    days = pd.DatetimeIndex(sorted(td.unique()))
    di = days.get_indexer(td)
    shape = (len(days), MINUTES_PER_DAY)
    mats = {}
    for k in ("open", "high", "low", "close"):
        a = np.full(shape, np.nan)
        a[di, off] = m[k].to_numpy(float)
        mats[k] = a
    cov = np.isfinite(mats["close"]).mean(axis=1)
    g = DayGrid(days, mats["open"], mats["high"], mats["low"], mats["close"], cov,
                pd.DataFrame(index=days))
    g.daily = daily_features(g)
    if min_coverage > 0:
        g = g.subset(g.coverage >= min_coverage)
    return g


def _nanfirst(a):
    idx = np.argmax(np.isfinite(a), axis=1)
    out = a[np.arange(len(a)), idx]
    out[~np.isfinite(a).any(axis=1)] = np.nan
    return out


def _nanlast(a):
    rev = a[:, ::-1]
    return _nanfirst(rev)


def daily_features(g: DayGrid) -> pd.DataFrame:
    """Per-trading-day OHLC and *lagged* features (known before the day starts)."""
    with np.errstate(all="ignore"):
        d = pd.DataFrame(index=g.days)
        d["open"] = _nanfirst(g.o)
        d["high"] = np.nanmax(g.h, axis=1)
        d["low"] = np.nanmin(g.l, axis=1)
        d["close"] = _nanlast(g.c)
        rth = slice(hhmm_to_offset("09:30"), hhmm_to_offset("16:00"))
        d["rth_close"] = _nanlast(g.c[:, rth])
    prev_close = d["close"].shift(1)
    # Unadjusted front-month data: the quarterly roll appears as an opening gap
    # (verified: never mid-session). Treat such gaps as contract switches,
    # back-adjust the daily close series and ignore the gap in true range.
    gap = d["open"] - prev_close
    hl = d["high"] - d["low"]
    in_window = d.index.month.isin([3, 6, 9, 12]) & (d.index.day >= 5) & (d.index.day <= 20)
    roll = (gap.abs() > 0.25 * hl.rolling(14, min_periods=5).mean().shift(1)) & in_window
    d["roll_gap"] = roll
    adj = gap.where(roll, 0.0).fillna(0.0)
    # add all *future* roll gaps to past closes (back-adjustment)
    back = adj[::-1].cumsum()[::-1].shift(-1).fillna(0.0)
    d["close_adj"] = d["close"] + back
    prev_close_eff = prev_close.where(~roll, d["open"])
    tr = pd.concat([hl, (d["high"] - prev_close_eff).abs(),
                    (d["low"] - prev_close_eff).abs()], axis=1).max(axis=1)
    # Everything below uses information up to the PREVIOUS trading day only.
    ca = d["close_adj"]
    d["atr14_prev"] = tr.rolling(14, min_periods=10).mean().shift(1)
    d["prev_close"] = prev_close
    # lagged levels expressed in the CURRENT day's contract (subtract back[t])
    d["prev_close_adj"] = ca.shift(1) - back
    d["sma20_prev"] = ca.rolling(20, min_periods=15).mean().shift(1) - back
    d["sma50_prev"] = ca.rolling(50, min_periods=40).mean().shift(1) - back
    d["ret5_prev"] = (ca / ca.shift(5) - 1).shift(1)
    return d


def flag_roll_days(g: DayGrid) -> pd.Series:
    """Trading days that open with a contract-roll gap: |open - previous close|
    > 0.25 x average daily range, inside a quarterly roll window (Mar/Jun/Sep/
    Dec, days 5-20). TOS /NQ is unadjusted, so the roll appears as a gap equal
    to the calendar spread. Intraday strategies are unaffected because the
    switch was verified to happen only at the 18:00 session boundary."""
    return g.daily["roll_gap"].astype(bool)
