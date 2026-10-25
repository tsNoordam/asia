"""Performance statistics.

Units and time bases (all P&L is per ONE contract, USD, net of costs):
* Trade-level: avg_usd, avg_win, avg_loss, win_rate, pf, t_stat.
  `t_stat` = mean / (std / sqrt(n)) over TRADES. It assumes trades are
  independent and identically distributed; it ignores that up to two trades
  share a session and that outcomes may be serially dependent. Use the
  daily-level `inference()` results for inference.
* Daily-level: one value per trading day in the evaluation period, including
  zero-trade days. `sharpe` = mean / std of daily P&L x sqrt(252). No risk-free
  rate is subtracted (futures P&L is an excess return).
* Equity / drawdown: cumulative daily P&L that STARTS AT 0 at the beginning of
  each evaluation period. Max drawdown is the largest fall from the running
  peak, where the peak includes the starting value 0, so losses from the first
  day onward count. Each period (TRAIN / VAL / OOS / FULL) is measured
  separately from its own zero baseline.
* Exposure: minutes in a position / (trading days x 1,380 Globex minutes).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .data import MINUTES_PER_DAY


def daily_pnl(trades: pd.DataFrame, days: pd.DatetimeIndex) -> pd.Series:
    """Net USD P&L per trading day in `days` (zero on days without trades).
    Raises if any trade falls outside `days`, which would otherwise be dropped
    silently from the daily series while still counted in trade totals."""
    if len(trades) == 0:
        return pd.Series(0.0, index=days)
    outside = ~trades["day"].isin(days)
    if outside.any():
        raise ValueError(f"{int(outside.sum())} trade(s) fall outside the evaluation days")
    return trades["usd"].groupby(trades["day"]).sum().reindex(days, fill_value=0.0).astype(float)


def max_drawdown(daily: pd.Series) -> float:
    """Largest peak-to-trough fall of cumulative P&L starting from 0 (<= 0)."""
    if len(daily) == 0:
        return 0.0
    eq = np.concatenate([[0.0], np.cumsum(np.asarray(daily, float))])
    return float(np.min(eq - np.maximum.accumulate(eq)))


def summarize(trades: pd.DataFrame, days: pd.DatetimeIndex) -> dict:
    n = len(trades)
    out = {"trades": n, "days": len(days)}
    if n == 0:
        out.update(net_usd=0.0, pf=float("nan"), win_rate=float("nan"), avg_usd=float("nan"),
                   avg_win=float("nan"), avg_loss=float("nan"), t_stat=float("nan"),
                   sharpe=float("nan"), max_dd_usd=0.0, exposure=0.0, avg_pts=float("nan"))
        return out
    u = trades["usd"]
    wins, losses = u[u > 0], u[u <= 0]
    daily = daily_pnl(trades, days)
    dd = max_drawdown(daily)
    sd = daily.std(ddof=1)
    out.update(
        net_usd=float(u.sum()),
        pf=float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf"),
        win_rate=float((u > 0).mean()),
        avg_usd=float(u.mean()),
        avg_pts=float(trades["pts"].mean()),
        avg_win=float(wins.mean()) if len(wins) else float("nan"),
        avg_loss=float(losses.mean()) if len(losses) else float("nan"),
        t_stat=float(u.mean() / (u.std(ddof=1) / math.sqrt(n))) if n > 2 and u.std() > 0 else float("nan"),
        sharpe=float(daily.mean() / sd * math.sqrt(252)) if sd > 0 else float("nan"),
        max_dd_usd=float(dd),
        exposure=float(trades["hold_min"].sum() / (len(days) * MINUTES_PER_DAY)),
        long_n=int((trades["side"] > 0).sum()),
        long_usd=float(u[trades["side"] > 0].sum()),
        short_n=int((trades["side"] < 0).sum()),
        short_usd=float(u[trades["side"] < 0].sum()),
    )
    return out


def _acf(x: np.ndarray, lags: int) -> list:
    x = x - x.mean()
    den = float(np.dot(x, x))
    if den == 0:
        return [float("nan")] * lags
    return [float(np.dot(x[:-k], x[k:]) / den) for k in range(1, lags + 1)]


def newey_west_se(x: np.ndarray, lags: int) -> float:
    """HAC standard error of the mean with Bartlett weights."""
    x = np.asarray(x, float)
    T = len(x)
    e = x - x.mean()
    s = float(np.dot(e, e)) / T
    for k in range(1, min(lags, T - 1) + 1):
        s += 2 * (1 - k / (lags + 1)) * float(np.dot(e[:-k], e[k:])) / T
    return math.sqrt(max(s, 0.0) / T)


def _block_indices(T: int, b: int, n_boot: int, rng) -> np.ndarray:
    """Circular block bootstrap index matrix (n_boot x T)."""
    nb = -(-T // b)
    starts = rng.integers(0, T, size=(n_boot, nb))
    idx = (starts[:, :, None] + np.arange(b)[None, None, :]) % T
    return idx.reshape(n_boot, nb * b)[:, :T]


def inference(trades: pd.DataFrame, days: pd.DatetimeIndex, n_boot: int = 5000, seed: int = 7,
              block_len: int | None = None) -> dict:
    """Daily-level inference that does not assume independent trades.

    * Daily P&L series over all trading days (zero-trade days included).
    * Newey-West (Bartlett) HAC t-stat of the mean daily P&L, lag rule
      floor(4 (T/100)^(2/9)).
    * Circular block bootstrap over TRADING DAYS (block length default
      ceil(T^(1/3)); results also reported for 1, 5 and 20 days). Each resample
      keeps whole days, so trades of the same session stay together. Gives 95%
      percentile CIs for mean daily P&L and for mean P&L per trade
      (= resampled total P&L / resampled trade count).
    * `p_boot_le0` = share of bootstrap means <= 0: a descriptive measure of
      sampling uncertainty, NOT a test that corrects for the ~7,000
      configurations searched before these rules were chosen.
    """
    d = daily_pnl(trades, days).to_numpy()
    cnt = (trades["day"].value_counts().reindex(days, fill_value=0).to_numpy()
           if len(trades) else np.zeros(len(days)))
    T = len(d)
    out = {"T_days": T, "trades": int(cnt.sum())}
    if T < 10 or cnt.sum() == 0:
        return out
    L = int(math.floor(4 * (T / 100) ** (2 / 9)))
    se_nw = newey_west_se(d, L)
    sd = d.std(ddof=1)
    b = block_len or max(1, math.ceil(T ** (1 / 3)))
    rng = np.random.default_rng(seed)
    out.update(
        daily_mean_usd=float(d.mean()), daily_sd_usd=float(sd),
        daily_t_iid=float(d.mean() / (sd / math.sqrt(T))) if sd > 0 else float("nan"),
        nw_lags=L, daily_t_nw=float(d.mean() / se_nw) if se_nw > 0 else float("nan"),
        acf=_acf(d, 5), block_len=b,
    )
    for bl in sorted({b, 1, 5, 20}):
        idx = _block_indices(T, bl, n_boot, rng)
        dm = d[idx].mean(axis=1)
        tot, n = d[idx].sum(axis=1), cnt[idx].sum(axis=1)
        tm = np.where(n > 0, tot / np.maximum(n, 1), np.nan)
        key = "" if bl == b else f"_b{bl}"
        out[f"daily_mean_ci95{key}"] = [float(np.percentile(dm, 2.5)), float(np.percentile(dm, 97.5))]
        out[f"trade_mean_ci95{key}"] = [float(np.nanpercentile(tm, 2.5)), float(np.nanpercentile(tm, 97.5))]
        if bl == b:
            out["p_boot_le0"] = float((dm <= 0).mean())
    return out


def by_year(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    g = trades.groupby(trades["day"].dt.year)["usd"]
    return pd.DataFrame({"trades": g.size(), "net_usd": g.sum(), "avg_usd": g.mean(),
                         "win_rate": g.apply(lambda s: (s > 0).mean())})


def fmt(s: dict) -> str:
    return (f"n={s['trades']:4d} net=${s['net_usd']:>10,.0f} PF={s['pf']:.2f} win={s['win_rate']:.1%} "
            f"avg=${s['avg_usd']:>7.1f} t={s['t_stat']:.2f} SR={s['sharpe']:.2f} DD=${s['max_dd_usd']:,.0f}")
