"""Gross -> Net bridge: the daily trading costs charged against gross PnL.

Rates in config are ANNUAL; charged daily on the prior day's exposure via
``dt = 1/252``. PM Net excludes center cost (a fund overhead) by design --
see ``economics.py`` and the methodology docs. ::

    financing_{pm,t}  = financing_rate * gross_exposure_{pm,t-1} * dt
    borrow_{pm,t}     = borrow_rate    * short_notional_{pm,t-1} * dt
    commission_{pm,t} = commission_bps/1e4 * traded_notional_{pm,t}
    pm_net_t          = pm_gross_t - financing_t - borrow_t - commission_t
"""
from __future__ import annotations

import pandas as pd

TRADING_DAYS = 252
DT = 1.0 / TRADING_DAYS


def add_costs(pm_daily: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Append daily cost columns and ``net_pnl`` to a per-PM daily frame.

    Args:
        pm_daily: output of :func:`src.engine.pnl.pm_daily_gross` with columns
            ``[date, pm_id, gross_pnl, gross_exposure, short_notional, traded_notional]``.
            ``gross_exposure`` and ``short_notional`` are prior-day (t-1) values.
        cfg: parsed config; reads ``cfg['costs']``.

    Returns:
        The frame with added columns ``[financing, borrow, commission, total_cost, net_pnl]``.
    """
    c = cfg["costs"]
    df = pm_daily.copy()
    df["financing"] = c["financing_rate"] * df["gross_exposure"] * DT
    df["borrow"] = c["borrow_rate"] * df["short_notional"] * DT
    df["commission"] = (c["commission_bps"] / 1e4) * df["traded_notional"]
    df["total_cost"] = df["financing"] + df["borrow"] + df["commission"]
    df["net_pnl"] = df["gross_pnl"] - df["total_cost"]
    return df


def bridge_components(pm_net_daily: pd.DataFrame, pm_ids: list[str] | None = None) -> dict:
    """Summed Gross -> PM Net bridge components for a set of PMs (or all).

    Returns a dict of period totals suitable for a component bar chart, with the
    cost entries stored as negative numbers (deductions).
    """
    df = pm_net_daily
    if pm_ids is not None:
        df = df[df["pm_id"].isin(pm_ids)]
    return {
        "Gross PnL": float(df["gross_pnl"].sum()),
        "Financing": -float(df["financing"].sum()),
        "Borrow": -float(df["borrow"].sum()),
        "Commission": -float(df["commission"].sum()),
        "Net PnL": float(df["net_pnl"].sum()),
    }
