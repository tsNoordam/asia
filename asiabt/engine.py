"""Event-driven, per-trading-day backtest engine for Asian-range strategies.

Execution assumptions (all configurable through `Costs` / `Params`):

* Signals are evaluated only on the CLOSE of completed `tf`-minute signal bars
  (built from 1-minute bars, aligned to the 18:00 session start). A market
  entry is filled at the OPEN of the next 1-minute bar, never at the signal
  bar's close, plus `slip_ticks` adverse slippage.
* The Asian range is the high/low of 1-minute bars in [range_start,
  range_end). It becomes available only after the bar starting at
  range_end - 1 minute has closed, so the first possible signal bar closes at
  range_end + tf.
* Stops are stop-market orders: filled at the stop price minus slippage, or at
  the bar open (minus slippage) if the bar gaps through the stop.
* Targets are limit orders: filled at the limit price only if the bar trades
  THROUGH it by `limit_through_ticks` (queue-position haircut), no slippage.
* If a single 1-minute bar touches both stop and target, the STOP is assumed
  to fill first (conservative).
* All positions are closed with a market order at the open of the
  `flat_time` bar (or the first later bar with data).
* One contract per trade; P&L is reported in index points and USD.
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np
import pandas as pd

from .data import DayGrid, hhmm_to_offset


@dataclasses.dataclass(frozen=True)
class Costs:
    tick: float = 0.25
    point_value: float = 20.0          # NQ $20/pt (MNQ $2/pt)
    commission_rt: float = 5.0         # USD per contract round turn incl. exchange/NFA fees
    slip_ticks: float = 1.0            # adverse ticks per side for market and stop fills
    limit_through_ticks: float = 1.0   # price must trade through a limit by this much to fill


@dataclasses.dataclass(frozen=True)
class Params:
    mode: str = "breakout"            # breakout | fade | hybrid | timed
    range_start: str = "18:00"
    range_end: str = "00:00"
    entry_cutoff: str = "08:00"       # no new entries at/after this time
    flat_time: str = "11:00"          # all positions closed at this time
    tf: int = 5                       # signal bar length, minutes
    max_trades: int = 1               # per session
    direction: str = "both"           # both | long | short
    min_range_atr: float = 0.0        # day filter on Asian range width / ATR14(prev)
    max_range_atr: float = 99.0
    trend_filter: str = "none"        # none | with | against  (vs. prior-day SMA20)
    # --- breakout -------------------------------------------------------
    bo_buffer_atr: float = 0.0        # signal close must exceed boundary by this x ATR
    bo_entry: str = "market"          # market | retest (limit at the broken boundary)
    bo_stop: str = "opposite"         # opposite | mid | atr
    bo_stop_atr: float = 0.5
    bo_target_r: float = 0.0          # 0 = no target, exit on time
    # --- fade (mean reversion) -----------------------------------------
    fd_min_ext: float = 0.0           # min excursion beyond the boundary ...
    fd_max_ext: float = 99.0          # ... and max excursion (breakout-strength filter)
    fd_ext_unit: str = "atr"          # atr | range
    fd_stop_buffer_atr: float = 0.05  # stop beyond the excursion extreme
    fd_target: str = "mid"            # mid | opposite | r
    fd_target_r: float = 1.0
    # --- hybrid ---------------------------------------------------------
    hybrid_thr: float = 0.35          # range/ATR below -> breakout mode, else fade mode
    # --- timed benchmark --------------------------------------------------
    timed_side: int = 1               # +1 long / -1 short, enter at range_end, exit flat_time
    # --- data hygiene -----------------------------------------------------
    min_range_cov: float = 0.9        # skip days with <90% of range minutes present
    min_trade_cov: float = 0.8

    def replace(self, **kw) -> "Params":
        return dataclasses.replace(self, **kw)


TRADE_COLS = ["day", "side", "mode", "sig_off", "entry_off", "entry_px", "exit_off", "exit_px",
              "reason", "stop", "target", "risk_pts", "pts", "usd", "mae_pts", "mfe_pts",
              "range_hi", "range_lo", "range_atr", "atr", "hold_min"]


def _first_valid(a: np.ndarray, start: int, end: int) -> int:
    for j in range(start, min(end, len(a))):
        if a[j] == a[j]:  # not NaN
            return j
    return -1


def _simulate_exit(o, h, l, c, e, side, entry_px, stop, target, flat, costs):
    """Walk 1-minute bars from entry bar `e`. Returns (exit_off, exit_px, reason, mae, mfe)."""
    slip = costs.slip_ticks * costs.tick
    thru = costs.limit_through_ticks * costs.tick
    mae = 0.0
    mfe = 0.0
    last_c = entry_px
    for j in range(e, flat):
        oj, hj, lj, cj = o[j], h[j], l[j], c[j]
        if oj != oj:
            continue
        if j > e:  # gap through stop / target at the open
            if side > 0 and oj <= stop:
                return j, oj - slip, "stop_gap", min(mae, oj - entry_px), mfe
            if side < 0 and oj >= stop:
                return j, oj + slip, "stop_gap", min(mae, entry_px - oj), mfe
            if target == target:
                if side > 0 and oj >= target + thru:
                    return j, oj, "target_gap", mae, max(mfe, oj - entry_px)
                if side < 0 and oj <= target - thru:
                    return j, oj, "target_gap", mae, max(mfe, entry_px - oj)
        adv = (lj - entry_px) if side > 0 else (entry_px - hj)
        fav = (hj - entry_px) if side > 0 else (entry_px - lj)
        mae = min(mae, adv)
        mfe = max(mfe, fav)
        hit_stop = (lj <= stop) if side > 0 else (hj >= stop)
        hit_tgt = target == target and ((hj >= target + thru) if side > 0 else (lj <= target - thru))
        if hit_stop:  # stop first if both touched in the same bar
            return j, (stop - slip) if side > 0 else (stop + slip), "stop", mae, mfe
        if hit_tgt:
            return j, target, "target", mae, mfe
        last_c = cj
    jx = _first_valid(o, flat, len(o))
    if jx >= 0:
        px = o[jx]
    else:
        jx, px = flat, last_c
    return jx, px - slip * side, "time", mae, mfe


def run(grid: DayGrid, p: Params, costs: Costs = Costs()) -> pd.DataFrame:
    rs, re = hhmm_to_offset(p.range_start), hhmm_to_offset(p.range_end)
    cut, flat = hhmm_to_offset(p.entry_cutoff), hhmm_to_offset(p.flat_time)
    assert rs < re <= cut <= flat, "session times must be ordered within the trading day"
    tf = p.tf
    slip = costs.slip_ticks * costs.tick
    thru = costs.limit_through_ticks * costs.tick
    daily = grid.daily
    atr_all = daily["atr14_prev"].to_numpy()
    sma_all = daily["sma20_prev"].to_numpy()
    pc_all = daily["prev_close_adj"].to_numpy()
    rows = []
    for i in range(len(grid)):
        o, h, l, c = grid.o[i], grid.h[i], grid.l[i], grid.c[i]
        atr = atr_all[i]
        if not (atr == atr) or atr <= 0:
            continue
        rng_ok = np.isfinite(c[rs:re]).mean() >= p.min_range_cov
        trd_ok = np.isfinite(c[re:flat]).mean() >= p.min_trade_cov
        if not (rng_ok and trd_ok):
            continue
        RH, RL = np.nanmax(h[rs:re]), np.nanmin(l[rs:re])
        W = RH - RL
        ratio = W / atr
        if ratio < p.min_range_atr or ratio > p.max_range_atr or W <= 0:
            continue
        mode = p.mode
        if mode == "hybrid":
            mode = "breakout" if ratio < p.hybrid_thr else "fade"
        trend = 0
        if sma_all[i] == sma_all[i] and pc_all[i] == pc_all[i]:
            trend = 1 if pc_all[i] > sma_all[i] else -1
        allow_long = p.direction in ("both", "long")
        allow_short = p.direction in ("both", "short")
        if p.trend_filter == "with" and trend != 0:
            allow_long &= trend > 0
            allow_short &= trend < 0
        elif p.trend_filter == "against" and trend != 0:
            allow_long &= trend < 0
            allow_short &= trend > 0
        day = grid.days[i]
        base = dict(day=day, mode=mode, range_hi=RH, range_lo=RL, range_atr=ratio, atr=atr)

        def record(side, sig_off, e, entry_px, stop, target):
            xo, xp, why, mae, mfe = _simulate_exit(o, h, l, c, e, side, entry_px, stop, target, flat, costs)
            pts = side * (xp - entry_px)
            rows.append({**base, "side": side, "sig_off": sig_off, "entry_off": e, "entry_px": entry_px,
                         "exit_off": xo, "exit_px": xp, "reason": why, "stop": stop, "target": target,
                         "risk_pts": abs(entry_px - stop), "pts": pts,
                         "usd": pts * costs.point_value - costs.commission_rt,
                         "mae_pts": mae, "mfe_pts": mfe, "hold_min": xo - e})
            return xo

        if mode == "timed":
            e = _first_valid(o, re, flat)
            if e < 0:
                continue
            side = p.timed_side
            record(side, re - 1, e, o[e] + slip * side, -math.inf if side > 0 else math.inf, math.nan)
            continue

        n_tr = 0
        b = re
        hi_since, lo_since = -math.inf, math.inf
        while b + tf <= cut and n_tr < p.max_trades:
            seg_h, seg_l, seg_c = h[b:b + tf], l[b:b + tf], c[b:b + tf]
            if not np.isfinite(seg_c).any():
                b += tf
                continue
            bh, bl = np.nanmax(seg_h), np.nanmin(seg_l)
            bc = seg_c[np.isfinite(seg_c)][-1]
            hi_since, lo_since = max(hi_since, bh), min(lo_since, bl)
            sig_end = b + tf  # first minute after the signal bar closed
            side = 0
            if mode == "breakout":
                buf = p.bo_buffer_atr * atr
                if allow_long and bc > RH + buf:
                    side = 1
                elif allow_short and bc < RL - buf:
                    side = -1
                if side:
                    if p.bo_entry == "retest":
                        lvl = RH if side > 0 else RL
                        e = -1
                        for j in range(sig_end, cut):
                            if l[j] == l[j] and ((side > 0 and l[j] <= lvl - thru) or (side < 0 and h[j] >= lvl + thru)):
                                e = j
                                break
                        if e < 0:
                            break  # retest never came: no trade this session
                        entry_px = min(lvl, o[e]) if side > 0 else max(lvl, o[e])
                    else:
                        e = _first_valid(o, sig_end, flat)
                        if e < 0:
                            break
                        entry_px = o[e] + slip * side
                    if p.bo_stop == "opposite":
                        stop = RL if side > 0 else RH
                    elif p.bo_stop == "mid":
                        stop = (RH + RL) / 2
                    else:
                        stop = entry_px - side * p.bo_stop_atr * atr
                    risk = side * (entry_px - stop)
                    if risk <= 0:  # entry already beyond the stop: order rejected
                        b = sig_end
                        continue
                    target = entry_px + side * p.bo_target_r * risk if p.bo_target_r > 0 else math.nan
                    xo = record(side, sig_end - 1, e, entry_px, stop, target)
                    n_tr += 1
                    hi_since, lo_since = -math.inf, math.inf
                    b = sig_end if xo < sig_end else sig_end + ((xo - sig_end) // tf + 1) * tf
                    continue
            elif mode == "fade":
                unit = atr if p.fd_ext_unit == "atr" else W
                ext_up, ext_dn = hi_since - RH, RL - lo_since
                up_ok = allow_short and p.fd_min_ext * unit <= ext_up <= p.fd_max_ext * unit and ext_up > 0
                dn_ok = allow_long and p.fd_min_ext * unit <= ext_dn <= p.fd_max_ext * unit and ext_dn > 0
                if up_ok and RL < bc < RH:
                    side = -1
                elif dn_ok and RL < bc < RH:
                    side = 1
                if side:
                    e = _first_valid(o, sig_end, flat)
                    if e < 0:
                        break
                    entry_px = o[e] + slip * side
                    buf = p.fd_stop_buffer_atr * atr
                    stop = (hi_since + buf) if side < 0 else (lo_since - buf)
                    risk = side * (entry_px - stop)
                    if p.fd_target == "mid":
                        target = (RH + RL) / 2
                    elif p.fd_target == "opposite":
                        target = RL if side < 0 else RH
                    else:
                        target = entry_px + side * p.fd_target_r * risk
                    if risk <= 0 or side * (target - entry_px) <= 0:
                        b = sig_end  # stop or target already passed at entry: skip
                        continue
                    xo = record(side, sig_end - 1, e, entry_px, stop, target)
                    n_tr += 1
                    hi_since, lo_since = -math.inf, math.inf
                    b = sig_end if xo < sig_end else sig_end + ((xo - sig_end) // tf + 1) * tf
                    continue
            b += tf
    return pd.DataFrame(rows, columns=TRADE_COLS)
