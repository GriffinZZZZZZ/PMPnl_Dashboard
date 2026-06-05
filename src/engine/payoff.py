"""Per-PM compensation: high-water-mark crystallization on cumulative net PnL.

For each PM, comp crystallizes against a running high-water mark and never
reverses (no clawback), so accrued comp is monotonically non-decreasing::

    cum_net_{pm,t}      = sum_{s<=t} pm_net
    peak_{pm,t}         = max(initial_HWM, max_{s<=t} cum_net)        # running HWM
    hurdle_amt_{pm,t}   = hurdle_rate * allocated_capital * (t * dt)  # time-scaled, small/0
    accrued_comp_{pm,t} = payout_ratio * max(0, peak - initial_HWM - hurdle_amt)
    daily_comp_{pm,t}   = accrued_comp_t - accrued_comp_{t-1}   (>= 0)
    total_comp          = sum_pm accrued_comp_{pm,T}

This models comp as a GAAP liability that grows daily with PnL rather than a
year-end calculation. ``accrued_comp`` is wrapped in a running max so the
documented non-decreasing / ``daily_comp >= 0`` invariant holds even when a
small time-scaled hurdle would otherwise dip the raw value.
"""
from __future__ import annotations

import pandas as pd

from src.engine.pnl import add_cumulative

TRADING_DAYS = 252
DT = 1.0 / TRADING_DAYS


def compute_payoff(
    pm_net_daily: pd.DataFrame,
    pms: pd.DataFrame,
    payout_ratio_override: float | None = None,
) -> pd.DataFrame:
    """Compute the daily accrued-comp series per PM.

    Args:
        pm_net_daily: per-PM daily frame containing ``[date, pm_id, net_pnl]``.
        pms: roster with ``[pm_id, payout_ratio, hurdle_rate, initial_HWM, allocated_capital]``.
        payout_ratio_override: if given, replaces every PM's payout ratio
            (used by the dashboard sensitivity slider). ``None`` uses each PM's own.

    Returns:
        Frame ``[date, pm_id, net_pnl, cum_net, hwm, hurdle_amt, accrued_comp, daily_comp]``.
    """
    df = add_cumulative(pm_net_daily[["date", "pm_id", "net_pnl"]], "net_pnl", "pm_id", "cum_net")

    meta = pms.set_index("pm_id")
    df = df.join(
        meta[["payout_ratio", "hurdle_rate", "initial_HWM", "allocated_capital"]], on="pm_id"
    )
    if payout_ratio_override is not None:
        df["payout_ratio"] = payout_ratio_override

    grp = df.groupby("pm_id", sort=False)
    # Day ordinal t = 1..n within each PM (time-scaled hurdle).
    df["t"] = grp.cumcount() + 1
    df["hurdle_amt"] = df["hurdle_rate"] * df["allocated_capital"] * (df["t"] * DT)

    # Running high-water mark, floored at the initial HWM.
    df["hwm"] = grp["cum_net"].cummax().clip(lower=None)
    df["hwm"] = df[["hwm", "initial_HWM"]].max(axis=1)

    raw = df["payout_ratio"] * (df["hwm"] - df["initial_HWM"] - df["hurdle_amt"]).clip(lower=0)
    # Crystallization: comp never reverses -> running max enforces daily_comp >= 0.
    df["accrued_comp"] = raw.groupby(df["pm_id"]).cummax()
    df["daily_comp"] = df.groupby("pm_id", sort=False)["accrued_comp"].diff().fillna(
        df["accrued_comp"]
    )
    return df[
        ["date", "pm_id", "net_pnl", "cum_net", "hwm", "hurdle_amt", "accrued_comp", "daily_comp"]
    ]


def total_comp_by_pm(payoff_daily: pd.DataFrame) -> pd.DataFrame:
    """Final accrued comp per PM (the last day's accrued value)."""
    last = (
        payoff_daily.sort_values("date")
        .groupby("pm_id", as_index=False)
        .last()[["pm_id", "accrued_comp"]]
        .rename(columns={"accrued_comp": "total_comp"})
    )
    return last


def fund_total_comp(payoff_daily: pd.DataFrame) -> float:
    """Fund-wide total comp expense = sum of every PM's final accrued comp."""
    return float(total_comp_by_pm(payoff_daily)["total_comp"].sum())
