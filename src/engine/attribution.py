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
    # Drop columns that already exist in position_frame to avoid merge conflicts.
    inst_cols = [c for c in instruments.columns if c not in position_frame.columns or c == "ticker"]
    df = position_frame.merge(instruments[inst_cols], on="ticker", how="left")
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
    roster = pms[["pm_id", key, "pm_aum"]].drop_duplicates("pm_id")
    df = pm_net_daily.merge(roster[["pm_id", key]], on="pm_id", how="left")
    out = df.groupby(key, as_index=False)[["gross_pnl", "net_pnl"]].sum()
    cap = roster.groupby(key)["pm_aum"].sum()
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

    Columns: financing, borrow, commission, fx, center, total_cost, gross_pnl,
    capital, cost_ratio (NaN for gross ≤ 0), cost_pct_capital (always defined).
    Sorted by total_cost descending.
    """
    cost_cols = [c for c in ["financing", "borrow", "commission", "fx", "center", "capital_charge", "gross_pnl"]
                 if c in pm_net_daily.columns]
    if key == "pm_id":
        df = pm_net_daily.copy()
    else:
        roster = pms[["pm_id", key]].drop_duplicates("pm_id")
        df = pm_net_daily.merge(roster, on="pm_id", how="left")
    g = df.groupby(key, as_index=False)[cost_cols].sum()
    cost_sum_cols = [c for c in ["financing", "borrow", "commission", "fx", "center", "capital_charge"] if c in g.columns]
    g["total_cost"] = g[cost_sum_cols].sum(axis=1)
    # cost/gross: only defined when gross > 0 (losers show NaN -> "n/a" in UI)
    g["cost_ratio"] = g["total_cost"] / g["gross_pnl"].where(g["gross_pnl"] > 0)
    # cost/capital: always defined (use for sorting when gross is negative)
    cap_map = pms.groupby(key)["pm_aum"].sum() if key != "pm_id" else pms.set_index("pm_id")["pm_aum"]
    g["capital"] = g[key].map(cap_map)
    g["cost_pct_capital"] = g["total_cost"] / g["capital"]
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
    pm_name = pms.set_index("pm_id")["pm_name"]
    holders = pf.groupby("ticker")["pm_id"].apply(
        lambda s: ", ".join(sorted(pm_name.reindex(s.unique()).dropna().astype(str)))
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
    """Per-PM annualized return, volatility, and Sharpe ratio.

    Return = total net / capital; vol = std of daily net return * sqrt(252);
    Sharpe = annual_return / annual_vol (no risk-free rate adjustment for simplicity).
    """
    meta = pms.set_index("pm_id")
    rows = []
    for pm_id, g in pm_net_daily.groupby("pm_id"):
        cap = meta.loc[pm_id, "pm_aum"]
        daily_ret = g["net_pnl"] / cap
        annual_ret = float(g["net_pnl"].sum() / cap)
        annual_vol = float(daily_ret.std(ddof=0) * np.sqrt(TRADING_DAYS))
        sharpe = annual_ret / annual_vol if annual_vol > 0 else float("nan")
        rows.append(
            {
                "pm_id": pm_id,
                "pm_name": meta.loc[pm_id, "pm_name"],
                "pod_id": meta.loc[pm_id, "pod_id"],
                "annual_return": annual_ret,
                "annual_vol": annual_vol,
                "sharpe": sharpe,
            }
        )
    return pd.DataFrame(rows)


def concentration_table(
    position_frame: pd.DataFrame,
    prices: pd.DataFrame,
    pms: pd.DataFrame,
    aum_total: float,
    n: int = 10,
) -> pd.DataFrame:
    """Top ``n`` positions by |NMV / AUM| — a position-concentration risk view.

    NMV (net market value) = Σ_pm qty * price (signed, last date).
    ``nmv_pct_aum = |NMV| / AUM``. Returned sorted by ``nmv_pct_aum`` descending.
    """
    last_date = position_frame["date"].max()
    last = position_frame[position_frame["date"] == last_date].copy()
    last_price = prices[prices["date"] == last_date].set_index("ticker")["close_price"]
    last["nmv"] = last["quantity"] * last["ticker"].map(last_price).fillna(0.0)
    nmv = last.groupby("ticker")["nmv"].sum()
    pm_name = pms.set_index("pm_id")["pm_name"]
    holders = (
        last.groupby("ticker")["pm_id"]
        .apply(lambda s: ", ".join(sorted(pm_name.reindex(s.unique()).dropna().astype(str))))
    )
    out = pd.DataFrame({
        "ticker": nmv.index,
        "nmv": nmv.values,
        "nmv_pct_aum": (nmv.abs() / aum_total).values,
        "held_by": nmv.index.map(holders),
    }).sort_values("nmv_pct_aum", ascending=False).head(n).reset_index(drop=True)
    return out


def netting_cost_curve(
    payoff_daily: pd.DataFrame,
    pm_net_daily: pd.DataFrame,
    cfg: dict,
) -> pd.DataFrame:
    """Daily cumulative netting cost time series.

    netting_cost(t) = max(0, Σ_pm accrued_comp(t) - hypothetical_netted_comp(fund_cum_net(t)))
    Shows how netting risk builds over the year.
    """
    from src.config import blended_payout_ratio

    blended = blended_payout_ratio(cfg)
    n_days = cfg.get("n_business_days", TRADING_DAYS)
    period_fraction = n_days * DT
    sum_hwm0 = sum(pm.get("initial_HWM", 0) for pm in cfg["pms"])
    sum_hurdle = sum(
        pm["hurdle_rate"] * pm["allocated_capital"] * period_fraction for pm in cfg["pms"]
    )

    # Daily fund cumulative net
    cum_net = (
        pm_net_daily.groupby("date")["net_pnl"].sum().sort_index().cumsum()
    )
    # Daily fund total accrued comp
    total_comp_daily = payoff_daily.groupby("date")["accrued_comp"].sum().sort_index()

    df = pd.DataFrame({"cum_net": cum_net, "total_comp": total_comp_daily}).ffill()
    df["hyp_comp"] = blended * (df["cum_net"] - sum_hwm0 - sum_hurdle).clip(lower=0)
    df["netting_cost"] = (df["total_comp"] - df["hyp_comp"]).clip(lower=0)
    return df[["cum_net", "total_comp", "netting_cost"]]
