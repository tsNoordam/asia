"""Tests for the pre-registered exchange-data conversion (asiabt.independent)."""
import pandas as pd

from asiabt.independent import fill_quiet_minutes, front_month


def _bars(sym, start_utc, n, vol, px=100.0):
    idx = pd.date_range(start_utc, periods=n, freq="1min", tz="UTC")
    return pd.DataFrame({"open": px, "high": px + 1, "low": px - 1, "close": px, "volume": vol, "symbol": sym}, index=idx)


def test_front_month_uses_previous_day_volume_only():
    # trading day 1 (Mon 2019-03-11, session starts Sun 18:00 NY = 22:00 UTC during EDT)
    d1 = pd.concat([_bars("NQH9", "2019-03-10 22:00", 60, 100), _bars("NQM9", "2019-03-10 22:00", 60, 10, 105),
                    _bars("NQH9-NQM9", "2019-03-10 22:00", 60, 999)])
    # day 2: volume shifts to NQM9, but day 2 must still use NQH9 (chosen from day-1 volume)
    d2 = pd.concat([_bars("NQH9", "2019-03-11 22:00", 60, 5), _bars("NQM9", "2019-03-11 22:00", 60, 500, 105)])
    d3 = pd.concat([_bars("NQH9", "2019-03-12 22:00", 60, 5), _bars("NQM9", "2019-03-12 22:00", 60, 500, 105)])
    fm = front_month(pd.concat([d1, d2, d3]))
    td = (fm.index + pd.Timedelta(hours=6)).normalize()
    chosen = fm.groupby(td)["contract"].first()
    assert list(chosen.values) == ["NQH9", "NQH9", "NQM9"]
    assert not fm["contract"].str.contains("-").any()
    # NY conversion: 22:00 UTC in EDT is 18:00 NY
    assert fm.index.min() == pd.Timestamp("2019-03-10 18:00")


def test_fill_quiet_minutes_only_short_gaps():
    idx = pd.to_datetime(["2019-01-07 18:00", "2019-01-07 18:01", "2019-01-07 18:05", "2019-01-07 19:30"])
    m = pd.DataFrame({"open": [1, 2, 3, 4.0], "high": [1, 2, 3, 4.0], "low": [1, 2, 3, 4.0],
                      "close": [1, 2, 3, 4.0], "volume": [1, 1, 1, 1]}, index=idx)
    f = fill_quiet_minutes(m, max_fill=30)
    assert pd.Timestamp("2019-01-07 18:03") in f.index          # 3-minute gap filled
    assert f.loc["2019-01-07 18:03", "close"] == 2.0 and f.loc["2019-01-07 18:03", "volume"] == 0
    assert pd.Timestamp("2019-01-07 18:30") not in f.index      # 84-minute gap left missing


def test_preregistered_verdict_rule():
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "ev", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "evaluate_independent.py")
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    good = {"daily_t_nw": 2.5, "daily_mean_ci95": [1.0, 50.0], "daily_mean_usd": 20.0}
    years = [{"net_usd": 1.0}] * 7 + [{"net_usd": -1.0}] * 3
    assert ev.verdict(good, good, years, 10.0, 5.0)["supported"]
    assert not ev.verdict({**good, "daily_t_nw": 2.0}, good, years, 10.0, 5.0)["primary_pass"]
    assert not ev.verdict(good, {**good, "daily_mean_usd": -1.0}, years, 10.0, 5.0)["supported"]
    assert not ev.verdict(good, good, years, 10.0, -5.0)["supported"]
