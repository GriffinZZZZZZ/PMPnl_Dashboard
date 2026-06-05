"""Attribution & netting risk.

* PnL contribution by Pod / strategy / sector / position.
* Cost and loss attribution by type.
* **Netting cost** — the finance centerpiece. When Pod A makes +100 and Pod B
  loses -100, investors net 0, but the fund still owes A's payout. Defined as the
  comp actually owed to winners minus the comp the fund *would* owe if charged on
  its single netted book::

      hypothetical_netted_comp = blended_payout * max(0, fund_cum_net
                                   - sum(initial_HWM) - sum(hurdle_amt_T))
      netting_cost = max(0, total_comp - hypothetical_netted_comp)

  A positive value is real dollars paid on profit the fund did not keep.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import blended_payout_ratio

TRADING_DAYS = 252
DT = 1.0 / TRADING_DAYS


def contribution_by(
    position_frame: pd.DataFrame, instruments: pd.DataFrame, dimension: str
) -> pd.DataFrame:
    """Gross PnL contribution aggregated by an instrument dimension.

    Args:
        position_frame: output of :func:`src.engine.pnl.build_position_frame`.
        instruments: roster with ``[ticker, asset_class, sector, strategy_tag]``.
        dimension: one of ``asset_class``, ``sector``, ``strategy_tag``, ``ticker``.

    Returns:
        Frame ``[<dimension>, gross_pnl]`` sorted descending by PnL.
    """
    df = position_frame.merge(instruments, on="ticker", how="left")
    out = (
        df.groupby(dimension, as_index=False)["gross_pnl"].sum()
        .sort_values("gross_pnl", ascending=False)
        .reset_index(drop=True)
    )
    return out


def pnl_by_pod(pm_net_daily: pd.DataFrame, pms: pd.DataFrame) -> pd.DataFrame:
    """Total gross & net PnL by pod (additive roll-up of its PMs)."""
    df = pm_net_daily.merge(pms[["pm_id", "pod_id"]], on="pm_id", how="left")
    return (
        df.groupby("pod_id", as_index=False)[["gross_pnl", "net_pnl"]].sum()
        .sort_values("net_pnl", ascending=False)
        .reset_index(drop=True)
    )


def cost_by_type(pm_net_daily: pd.DataFrame) -> pd.DataFrame:
    """Total cost by type across the fund (financing / borrow / commission)."""
    totals = {
        "Financing": float(pm_net_daily["financing"].sum()),
        "Borrow": float(pm_net_daily["borrow"].sum()),
        "Commission": float(pm_net_daily["commission"].sum()),
    }
    return pd.DataFrame({"cost_type": list(totals), "cost": list(totals.values())})


def top_contributors(
    position_frame: pd.DataFrame, instruments: pd.DataFrame, n: int = 10
) -> pd.DataFrame:
    """Top ``n`` positive and top ``n`` negative positions by gross PnL."""
    by_ticker = contribution_by(position_frame, instruments, "ticker")
    top = by_ticker.head(n)
    bottom = by_ticker.tail(n)
    return pd.concat([top, bottom]).drop_duplicates().reset_index(drop=True)


def hypothetical_netted_comp(fund_net: float, cfg: dict) -> float:
    """Comp the fund *would* owe if charged on its single netted book.

    ``blended_payout * max(0, fund_net - sum(initial_HWM) - sum(hurdle_amt_T))``,
    where the period's hurdle for each PM is ``hurdle_rate * capital * period_fraction``.
    """
    blended = blended_payout_ratio(cfg)
    period_fraction = cfg.get("n_business_days", TRADING_DAYS) * DT
    sum_hwm0 = sum(pm.get("initial_HWM", 0) for pm in cfg["pms"])
    sum_hurdle = sum(
        pm["hurdle_rate"] * pm["allocated_capital"] * period_fraction for pm in cfg["pms"]
    )
    return float(blended * max(0.0, fund_net - sum_hwm0 - sum_hurdle))


def netting_cost(total_comp: float, fund_net: float, cfg: dict) -> float:
    """Comp paid on gains offset by other pods' losses (see module docstring)."""
    return float(max(0.0, total_comp - hypothetical_netted_comp(fund_net, cfg)))


def risk_return(pm_net_daily: pd.DataFrame, pms: pd.DataFrame) -> pd.DataFrame:
    """Per-PM annualized return (on capital) and annualized volatility.

    Used for the risk-return scatter. Return = total net / capital; volatility =
    std of daily net return * sqrt(252).
    """
    meta = pms.set_index("pm_id")
    rows = []
    for pm_id, g in pm_net_daily.groupby("pm_id"):
        cap = meta.loc[pm_id, "allocated_capital"]
        daily_ret = g["net_pnl"] / cap
        rows.append(
            {
                "pm_id": pm_id,
                "name": meta.loc[pm_id, "name"],
                "pod_id": meta.loc[pm_id, "pod_id"],
                "annual_return": float(g["net_pnl"].sum() / cap),
                "annual_vol": float(daily_ret.std(ddof=0) * np.sqrt(TRADING_DAYS)),
            }
        )
    return pd.DataFrame(rows)
