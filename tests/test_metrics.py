"""Tests for drawdown, equity baseline and daily-level inference."""
import numpy as np
import pandas as pd
import pytest

from asiabt.metrics import daily_pnl, inference, max_drawdown, summarize

DAYS = pd.bdate_range("2024-01-01", periods=6)


def _trades(rows):
    """rows: list of (day_index, usd)."""
    return pd.DataFrame({"day": [DAYS[i] for i, _ in rows], "usd": [u for _, u in rows],
                         "pts": [u / 20 for _, u in rows], "side": 1, "hold_min": 10})


def test_negative_first_day_counts_as_drawdown():
    s = summarize(_trades([(0, -500.0), (1, 200.0)]), DAYS)
    assert s["max_dd_usd"] == pytest.approx(-500.0)


def test_positive_first_day_then_decline():
    s = summarize(_trades([(0, 300.0), (1, -100.0), (2, -400.0)]), DAYS)
    assert s["max_dd_usd"] == pytest.approx(-500.0)


def test_no_trades_has_zero_drawdown():
    s = summarize(_trades([]).iloc[0:0], DAYS)
    assert s["max_dd_usd"] == 0.0 and s["trades"] == 0


def test_consecutive_losses_accumulate():
    s = summarize(_trades([(0, -100.0), (1, -200.0), (2, -300.0)]), DAYS)
    assert s["max_dd_usd"] == pytest.approx(-600.0)


def test_recovery_to_new_high_resets_peak():
    # equity: -100, 200 (new high), 50 -> worst is -150 from the 200 peak
    s = summarize(_trades([(0, -100.0), (1, 300.0), (2, -150.0)]), DAYS)
    assert s["max_dd_usd"] == pytest.approx(-150.0)


def test_multiple_trades_same_day_are_aggregated():
    d = daily_pnl(_trades([(0, -100.0), (0, 50.0), (2, 25.0)]), DAYS)
    assert list(d.values) == [-50.0, 0.0, 25.0, 0.0, 0.0, 0.0]


def test_split_period_boundaries_restart_at_zero():
    tr = _trades([(0, 400.0), (1, -100.0), (3, -300.0), (4, 100.0)])
    first, second = DAYS[:3], DAYS[3:]
    s1 = summarize(tr[tr.day.isin(first)], first)
    s2 = summarize(tr[tr.day.isin(second)], second)
    assert s1["max_dd_usd"] == pytest.approx(-100.0)
    # second period starts flat at 0; its first day loses 300 -> drawdown -300
    assert s2["max_dd_usd"] == pytest.approx(-300.0)


def test_trades_outside_evaluation_days_are_rejected():
    tr = _trades([(0, 100.0)])
    with pytest.raises(ValueError):
        summarize(tr, DAYS[1:])


def test_max_drawdown_function_directly():
    assert max_drawdown(pd.Series([-1.0, -1.0, 3.0, -2.0])) == pytest.approx(-2.0)
    assert max_drawdown(pd.Series([], dtype=float)) == 0.0


def test_inference_block_bootstrap_contains_true_mean_for_iid_noise():
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2020-01-01", periods=750)
    tr = pd.DataFrame({"day": days, "usd": rng.normal(10.0, 100.0, len(days)), "pts": 0.0,
                       "side": 1, "hold_min": 1})
    inf = inference(tr, days, n_boot=2000, seed=1)
    lo, hi = inf["daily_mean_ci95"]
    assert lo < 10.0 < hi
    assert inf["block_len"] >= 1
    assert abs(inf["acf"][0]) < 0.15
