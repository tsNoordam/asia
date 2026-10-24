"""Unit tests for session mapping and execution rules using synthetic bars."""
import math

import numpy as np
import pandas as pd
import pytest

from asiabt.data import MINUTES_PER_DAY, build_grid, hhmm_to_offset, load_minutes, offset_to_hhmm
from asiabt.engine import Costs, Params, _simulate_exit, run

NOCOST = Costs(commission_rt=0.0, slip_ticks=0.0, limit_through_ticks=0.0)


def test_offsets_roundtrip():
    assert hhmm_to_offset("18:00") == 0
    assert hhmm_to_offset("00:00") == 360
    assert hhmm_to_offset("02:00") == 480
    assert hhmm_to_offset("09:30") == 930
    assert hhmm_to_offset("16:59") == MINUTES_PER_DAY - 1
    for off in (0, 359, 360, 931, 1379):
        assert hhmm_to_offset(offset_to_hhmm(off)) == off


def _day_frame(trading_day: str, path):
    """1-minute bars for one trading day from a function offset->price."""
    start = pd.Timestamp(trading_day) - pd.Timedelta(hours=6)  # 18:00 previous day
    idx = pd.date_range(start, periods=MINUTES_PER_DAY, freq="1min")
    px = np.array([path(k) for k in range(MINUTES_PER_DAY)], float)
    return pd.DataFrame({"open": px, "high": px + 0.25, "low": px - 0.25, "close": px}, index=idx)


def _grid(frames, atr=100.0):
    m = pd.concat(frames)
    g = build_grid(m)
    g.daily["atr14_prev"] = atr
    g.daily["sma20_prev"] = np.nan
    g.daily["prev_close_adj"] = np.nan
    return g


def test_trading_day_labels_across_dst():
    # 2024-03-10 is the US spring-forward Sunday; the Monday session starts
    # Sunday 18:00 NY wall-clock time and must map to offset 0 of 2024-03-11.
    f = _day_frame("2024-03-11", lambda k: 100.0)
    g = build_grid(f)
    assert list(g.days) == [pd.Timestamp("2024-03-11")]
    assert np.isfinite(g.c[0]).all()


def test_range_has_no_lookahead_and_entry_is_next_open():
    rh = 110.0

    def path(k):
        if k < 360:                       # Asia 18:00-00:00 oscillates 90..110
            return 100 + 10 * math.sin(k / 20)
        if k < 400:
            return 100.0
        return 120.0 + (k - 400) * 0.01   # breakout at 00:40 and drift up

    g = _grid([_day_frame("2024-01-10", path)] * 1)
    tr = run(g, Params(mode="breakout", tf=5, flat_time="11:00"), NOCOST)
    assert len(tr) == 1
    t = tr.iloc[0]
    assert t.range_hi == pytest.approx(rh + 0.25, abs=0.01)
    # first close above the range is in the 5-min bar [400,405) -> entry at 405 open
    assert t.sig_off == 404 and t.entry_off == 405
    assert t.entry_px == pytest.approx(120.0 + 5 * 0.01)
    assert t.reason == "time" and t.exit_off == hhmm_to_offset("11:00")


def test_stop_first_when_both_hit_same_bar():
    o = np.array([100.0, 100.0, 100.0])
    h = np.array([100.0, 106.0, 100.0])
    l = np.array([100.0, 94.0, 100.0])
    c = o.copy()
    xo, xp, why, *_ = _simulate_exit(o, h, l, c, 0, 1, 100.0, 95.0, 105.0, 3, NOCOST)
    assert why == "stop" and xp == 95.0 and xo == 1


def test_gap_through_stop_fills_at_open_with_slippage():
    o = np.array([100.0, 90.0, 90.0])
    h, l, c = o + 0.5, o - 0.5, o
    costs = Costs(slip_ticks=1)
    xo, xp, why, *_ = _simulate_exit(o, h, l, c, 0, 1, 100.0, 95.0, math.nan, 3, costs)
    assert why == "stop_gap" and xp == pytest.approx(90.0 - 0.25)


def test_limit_target_requires_trade_through():
    o = np.array([100.0, 100.0, 100.0, 100.0])
    h = np.array([100.0, 105.0, 105.25, 100.0])
    l = o - 0.25
    c = o
    costs = Costs(limit_through_ticks=1, slip_ticks=0)
    xo, xp, why, *_ = _simulate_exit(o, h, l, c, 0, 1, 100.0, 90.0, 105.0, 4, costs)
    assert why == "target" and xo == 2 and xp == 105.0  # touch at bar 1 is not enough


def test_fade_requires_close_back_inside():
    def path(k):
        if k < 360:
            return 100 + 10 * math.sin(k / 20)   # range ~90..110
        if k < 380:
            return 115.0                          # excursion above
        return 105.0                              # back inside from 00:20

    g = _grid([_day_frame("2024-01-10", path)])
    tr = run(g, Params(mode="fade", fd_target="mid", tf=5), NOCOST)
    assert len(tr) == 1
    t = tr.iloc[0]
    assert t.side == -1 and t.sig_off == 384 and t.entry_off == 385
    assert t.stop == pytest.approx(115.25 + 0.05 * 100)


def test_stale_runs_are_removed(tmp_path):
    f = _day_frame("2024-01-10", lambda k: 100.0 + (k % 2) * 0.25)
    f.iloc[100:130, :] = 100.0  # 30 motionless minutes = recorder running while closed
    f.loc[f.index[100:130], ["high", "low"]] = 100.0
    p = tmp_path / "m.parquet"
    f.to_parquet(p)
    m = load_minutes(str(p), stale_run=10)
    assert len(m) < len(f) and len(f) - len(m) >= 29
