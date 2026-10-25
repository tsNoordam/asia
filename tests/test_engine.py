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


def test_breakeven_moves_stop_from_next_bar():
    # long from 100, stop 95, target 110, breakeven trigger at 103
    o = np.array([100.0, 101.0, 103.5, 101.0, 99.0])
    h = np.array([100.5, 103.0, 104.0, 101.5, 99.5])
    l = np.array([99.5, 100.5, 100.5, 99.5, 98.5])
    c = o.copy()
    xo, xp, why, *_ = _simulate_exit(o, h, l, c, 0, 1, 100.0, 95.0, 110.0, 5, NOCOST, be_px=103.0)
    # trigger reached in bar 1 -> stop = 100 from bar 2; bar 3 low 99.5 hits it
    assert why == "stop" and xo == 3 and xp == 100.0


def _random_days(n_days=30, seed=1):
    rng = np.random.default_rng(seed)
    frames = []
    px = 15000.0
    for d in pd.bdate_range("2024-01-08", periods=n_days):
        steps = rng.normal(0, 3.0, MINUTES_PER_DAY).cumsum() + px
        start = d - pd.Timedelta(hours=6)
        idx = pd.date_range(start, periods=MINUTES_PER_DAY, freq="1min")
        o = steps
        c = steps + rng.normal(0, 1.0, MINUTES_PER_DAY)
        h = np.maximum(o, c) + rng.uniform(0, 2, MINUTES_PER_DAY)
        l = np.minimum(o, c) - rng.uniform(0, 2, MINUTES_PER_DAY)
        frames.append(pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=idx))
        px = c[-1]
    return pd.concat(frames)


@pytest.mark.parametrize("mode", ["fade", "breakout", "hybrid"])
def test_no_lookahead_future_perturbation(mode):
    """Trades that exit before time T must be identical when every bar at or
    after T is replaced with different data."""
    m = _random_days()
    p = Params(mode=mode, max_trades=2, fd_min_ext=0.02, fd_max_ext=99.0)
    base = run(build_grid(m), p, Costs())
    cut_ts = m.index[len(m) // 2]
    m2 = m.copy()
    after = m2.index >= cut_ts
    m2.loc[after, ["open", "high", "low", "close"]] = m2.loc[after, ["open", "high", "low", "close"]] * 1.03 + 50
    pert = run(build_grid(m2), p, Costs())

    def exit_ts(t):
        return t["day"] - pd.Timedelta(hours=6) + pd.to_timedelta(t["exit_off"], unit="min")

    keep = lambda df: df[df.apply(exit_ts, axis=1) < cut_ts - pd.Timedelta(days=1)].reset_index(drop=True)
    a, b = keep(base), keep(pert)
    assert len(a) > 0
    pd.testing.assert_frame_equal(a, b)


def test_daily_features_use_only_past_days():
    m = _random_days(40)
    g1 = build_grid(m)
    m2 = m.copy()
    late = m2.index >= m2.index[-5 * MINUTES_PER_DAY]
    m2.loc[late, ["open", "high", "low", "close"]] *= 1.10
    g2 = build_grid(m2)
    cols = ["atr14_prev", "sma20_prev", "prev_close_adj", "ret5_prev"]
    # features of every day before the perturbed tail (incl. the first perturbed day) are unchanged
    pd.testing.assert_frame_equal(g1.daily[cols].iloc[:-4], g2.daily[cols].iloc[:-4])


# --- Stage 2: two-sided excursion ambiguity ---------------------------------
# Range 18:00-00:00 oscillates 90..110 (high/low +-0.25). ATR = 100, so with
# fd_min_ext = 0.02 an excursion needs >= 2 points; cap fd_max_ext = 0.3 -> 30 pts.

def _amb_grid(after):
    """`after(k)` -> (open, high, low, close) for offsets k >= 360."""
    start = pd.Timestamp("2024-01-10") - pd.Timedelta(hours=6)
    idx = pd.date_range(start, periods=MINUTES_PER_DAY, freq="1min")
    rows = []
    for k in range(MINUTES_PER_DAY):
        if k < 360:
            px = 100 + 10 * math.sin(k / 20)
            rows.append((px, px + 0.25, px - 0.25, px))
        else:
            rows.append(after(k))
    f = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    return _grid([f])


def _flat(px):
    return (px, px + 0.25, px - 0.25, px)


AMB = dict(mode="fade", tf=5, fd_min_ext=0.02, fd_max_ext=0.3, fd_target="opposite", max_trades=1)


def test_upper_excursion_only_gives_short():
    g = _amb_grid(lambda k: _flat(115.0) if k < 370 else _flat(105.0))
    for pol in ("legacy_short_first", "latest", "skip"):
        tr = run(g, Params(**AMB, fd_both_sides=pol), NOCOST)
        assert len(tr) == 1 and tr.iloc[0].side == -1 and not tr.iloc[0].ambiguous


def test_lower_excursion_only_gives_long():
    g = _amb_grid(lambda k: _flat(85.0) if k < 370 else _flat(95.0))
    for pol in ("legacy_short_first", "latest", "skip"):
        tr = run(g, Params(**AMB, fd_both_sides=pol), NOCOST)
        assert len(tr) == 1 and tr.iloc[0].side == 1 and not tr.iloc[0].ambiguous


def _both_same_minute(k):
    if k == 362:   # one 1-minute bar spikes through BOTH sides, closes inside
        return (100.0, 115.0, 85.0, 100.0)
    return _flat(100.0)


def test_both_sides_same_minute_legacy_reproduces_short_bias():
    tr = run(_amb_grid(_both_same_minute), Params(**AMB, fd_both_sides="legacy_short_first"), NOCOST)
    # the defect: the short is chosen purely by branch order
    assert len(tr) == 1 and tr.iloc[0].side == -1 and tr.iloc[0].ambiguous


def test_both_sides_same_minute_is_skipped_by_corrected_rules():
    for pol in ("latest", "skip"):
        tr = run(_amb_grid(_both_same_minute), Params(**AMB, fd_both_sides=pol), NOCOST)
        assert len(tr) == 0


def _both_different_bars(k):
    # up-sweep at 00:01, then a down-sweep at 00:03, both inside the first
    # 5-minute signal bar [00:00, 00:05), which closes back inside the range
    if k == 361:
        return (100.0, 115.0, 100.0, 112.0)
    if k == 363:
        return (100.0, 100.0, 85.0, 88.0)
    return _flat(100.0)


def test_both_sides_different_minutes_latest_fades_most_recent():
    tr = run(_amb_grid(_both_different_bars), Params(**AMB, fd_both_sides="latest"), NOCOST)
    assert len(tr) == 1 and tr.iloc[0].side == 1 and tr.iloc[0].ambiguous  # low was set last
    tr = run(_amb_grid(_both_different_bars), Params(**AMB, fd_both_sides="skip"), NOCOST)
    assert len(tr) == 0
    tr = run(_amb_grid(_both_different_bars), Params(**AMB, fd_both_sides="legacy_short_first"), NOCOST)
    assert tr.iloc[0].side == -1


def test_reentry_after_excursion_beyond_cap_is_not_faded():
    # 40-point excursion > 30-point cap, then a close back inside: no trade,
    # and the side stays disabled for the session (the extreme never shrinks)
    g = _amb_grid(lambda k: _flat(150.0) if k < 370 else _flat(105.0))
    for pol in ("legacy_short_first", "latest", "skip"):
        assert len(run(g, Params(**AMB, fd_both_sides=pol), NOCOST)) == 0
