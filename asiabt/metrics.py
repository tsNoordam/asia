"""Performance statistics.

Sharpe ratio: mean / std of DAILY USD P&L over every eligible trading day in
the evaluation period (days without a trade count as 0), annualised with
sqrt(252). No risk-free rate is subtracted (futures P&L is an excess return;
margin earns interest separately). It is a per-contract figure, independent of
account size.
Max drawdown: largest peak-to-trough fall of cumulative daily USD P&L.
Exposure: minutes in a position / (trading days x 1,380 Globex minutes).
"""
from __future__ import annotations

import math

import pandas as pd

from .data import MINUTES_PER_DAY


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
    daily = u.groupby(trades["day"]).sum().reindex(days, fill_value=0.0)
    eq = daily.cumsum()
    dd = (eq - eq.cummax()).min()
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


def by_year(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    g = trades.groupby(trades["day"].dt.year)["usd"]
    return pd.DataFrame({"trades": g.size(), "net_usd": g.sum(), "avg_usd": g.mean(),
                         "win_rate": g.apply(lambda s: (s > 0).mean())})


def fmt(s: dict) -> str:
    return (f"n={s['trades']:4d} net=${s['net_usd']:>10,.0f} PF={s['pf']:.2f} win={s['win_rate']:.1%} "
            f"avg=${s['avg_usd']:>7.1f} t={s['t_stat']:.2f} SR={s['sharpe']:.2f} DD=${s['max_dd_usd']:,.0f}")
