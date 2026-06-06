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
    position_frame: pd.DataFrame,
    instruments: pd.DataFrame,
    dimension: str,
    aum: float | None = None,
) -> pd.DataFrame:
    """Gross PnL contribution aggregated by an instrument dimension.

    Args:
        position_frame: output of :func:`src.engine.pnl.build_position_frame`.
        instruments: roster with ``[ticker, asset_class, sector, strategy_tag]``.
        dimension: one of ``asset_class``, ``sector``, ``strategy_tag``, ``ticker``.
        aum: if given, add a ``return_on_aum = gross_pnl / aum`` column.

    Returns:
        Frame ``[<dimension>, gross_pnl(, return_on_aum)]`` sorted descending by PnL.
    """
    df = position_frame.merge(instruments, on="ticker", how="left")
    out = (
        df.groupby(dimension, as_index=False)["gross_pnl"].sum()
        .sort_values("gross_pnl", ascending=False)
        .reset_index(drop=True)
    )
    if aum:
        out["return_on_aum"] = out["gross_pnl"] / aum
    return out


def pnl_by_group(
    pm_net_daily: pd.DataFrame, pms: pd.DataFrame, key: str = "pod_id"
) -> pd.DataFrame:
    """Gross/net PnL and return-on-capital by a grouping key (``pod_id`` or ``team_id``).

    Returns ``[<key>, gross_pnl, net_pnl, capital, return_on_capital]`` sorted by net.
    """
    roster = pms[["pm_id", key, "allocated_capital"]].drop_duplicates("pm_id")
    df = pm_net_daily.merge(roster[["pm_id", key]], on="pm_id", how="left")
    out = df.groupby(key, as_index=False)[["gross_pnl", "net_pnl"]].sum()
    cap = roster.groupby(key)["allocated_capital"].sum()
    out["capital"] = out[key].map(cap)
    out["return_on_capital"] = out["net_pnl"] / out["capital"]
    return out.sort_values("net_pnl", ascending=False).reset_index(drop=True)


def pnl_by_pod(pm_net_daily: pd.DataFrame, pms: pd.DataFrame) -> pd.DataFrame:
    """Total gross & net PnL by strategy pod (additive roll-up of its PMs)."""
    return pnl_by_group(pm_net_daily, pms, "pod_id")


def cost_by_type(pm_net_daily: pd.DataFrame) -> pd.DataFrame:
    """Total cost by type across the fund (financing / borrow / commission)."""
    totals = {
        "Financing": float(pm_net_daily["financing"].sum()),
        "Borrow": float(pm_net_daily["borrow"].sum()),
        "Commission": float(pm_net_daily["commission"].sum()),
    }
    return pd.DataFrame({"cost_type": list(totals), "cost": list(totals.values())})


def cost_table_by(pm_net_daily: pd.DataFrame, pms: pd.DataFrame, key: str = "pod_id") -> pd.DataFrame:
    """Cost breakdown + cost/gross ratio grouped by ``pod_id`` / ``team_id`` / ``pm_id``.

    Surfaces who is expensive: returns financing/borrow/commission/total_cost,
    gross_pnl, and ``cost_ratio = total_cost / gross_pnl``, sorted by total cost.
    """
    val_cols = ["financing", "borrow", "commission", "gross_pnl"]
    if key == "pm_id":
        df = pm_net_daily.copy()
    else:
        roster = pms[["pm_id", key]].drop_duplicates("pm_id")
        df = pm_net_daily.merge(roster, on="pm_id", how="left")
    g = df.groupby(key, as_index=False)[val_cols].sum()
    g["total_cost"] = g["financing"] + g["borrow"] + g["commission"]
    g["cost_ratio"] = g["total_cost"] / g["gross_pnl"].where(g["gross_pnl"] > 0)
    return g.sort_values("total_cost", ascending=False).reset_index(drop=True)


def position_table(
    position_frame: pd.DataFrame, instruments: pd.DataFrame, pms: pd.DataFrame
) -> pd.DataFrame:
    """Per-position gross PnL, return, and which PMs held it.

    ``position_return = total gross PnL / average daily gross exposure`` for the
    ticker; ``held_by`` lists the PM codes that traded it. Sorted by PnL so callers
    can take ``.head(n)`` (top contributors) and ``.tail(n)`` (detractors).
    """
    pf = position_frame
    pnl = pf.groupby("ticker")["gross_pnl"].sum()
    avg_expo = (
        pf.groupby(["date", "ticker"])["gross_exposure"].sum().groupby("ticker").mean()
    )
    name = pms.set_index("pm_id")["name"]
    holders = pf.groupby("ticker")["pm_id"].apply(
        lambda s: ", ".join(sorted(name.reindex(s.unique()).dropna().astype(str)))
    )
    strat = instruments.set_index("ticker")["strategy_tag"]
    out = pd.DataFrame({"ticker": pnl.index})
    out["strategy_tag"] = out["ticker"].map(strat)
    out["held_by"] = out["ticker"].map(holders)
    out["gross_pnl"] = out["ticker"].map(pnl)
    out["position_return"] = out["ticker"].map(pnl / avg_expo.replace(0, np.nan))
    return out.sort_values("gross_pnl", ascending=False).reset_index(drop=True)


def top_bottom_positions(
    position_frame: pd.DataFrame, instruments: pd.DataFrame, pms: pd.DataFrame, n: int = 10
) -> pd.DataFrame:
    """Top-``n`` and bottom-``n`` positions by gross PnL (with holders + return)."""
    tbl = position_table(position_frame, instruments, pms)
    return pd.concat([tbl.head(n), tbl.tail(n)]).drop_duplicates("ticker").reset_index(drop=True)


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
