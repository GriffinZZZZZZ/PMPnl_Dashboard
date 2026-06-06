"""Per-PM compensation: high-water-mark crystallization with a tiered schedule.

For each PM, comp crystallizes against a running high-water mark and never
reverses (no clawback), so accrued comp is monotonically non-decreasing. Two
structural features beyond a flat rate:

* **Loss carryforward** — a negative ``prior_year_pnl`` becomes
  ``loss_carryforward = max(0, -prior_year_pnl)`` that must be earned back this
  year before any comp accrues (it raises the comp threshold).
* **Tiered (structural) payout** — the contractual ``payout_ratio`` is the BASE
  rate; ``comp_tiers`` add marginal percentage points on higher bands of profit::

      cum_net_{pm,t}      = sum_{s<=t} pm_net
      peak_{pm,t}         = max(initial_HWM, max_{s<=t} cum_net)        # running HWM
      hurdle_amt_{pm,t}   = hurdle_rate * allocated_capital * (t * dt)
      profit_above_{pm,t} = max(0, peak - initial_HWM - hurdle_amt - loss_carryforward)
      accrued_comp_{pm,t} = tiered(profit_above; base=payout_ratio, comp_tiers)
      daily_comp_{pm,t}   = accrued_comp_t - accrued_comp_{t-1}   (>= 0)

This models comp as a GAAP liability that grows daily with PnL. ``accrued_comp``
is wrapped in a running max so the non-decreasing / ``daily_comp >= 0`` invariant
holds even when a growing hurdle would otherwise dip the raw value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.engine.pnl import add_cumulative

TRADING_DAYS = 252
DT = 1.0 / TRADING_DAYS

# Fallback when no tiers are configured: a single flat tier (base rate only).
_FLAT_TIERS = [{"upto": None, "add_pp": 0.0}]


def tiered_comp(profit_above: pd.Series, base_rate: pd.Series, tiers: list[dict]) -> pd.Series:
    """Vectorized marginal tiered compensation.

    For each row, comp = sum over tiers of ``(base_rate + add_pp) * width`` where
    ``width`` is the slice of ``profit_above`` that falls in that tier's band.

    Args:
        profit_above: profit above HWM (+ hurdle + carryforward), clipped at 0.
        base_rate: contractual base payout ratio (per row).
        tiers: ordered list of ``{upto, add_pp}``; ``upto=None`` marks the top band.

    Returns:
        A Series of comp aligned to ``profit_above``.
    """
    comp = pd.Series(0.0, index=profit_above.index)
    lower = 0.0
    for tier in tiers:
        upto = tier.get("upto")
        upper = float(upto) if upto is not None else np.inf
        width = (profit_above.clip(upper=upper) - lower).clip(lower=0.0)
        comp = comp + (base_rate + float(tier["add_pp"])) * width
        lower = upper
        if not np.isfinite(upper):
            break
    return comp


def compute_payoff(
    pm_net_daily: pd.DataFrame,
    pms: pd.DataFrame,
    cfg: dict,
    payout_ratio_override: float | None = None,
) -> pd.DataFrame:
    """Compute the daily accrued-comp series per PM.

    Args:
        pm_net_daily: per-PM daily frame containing ``[date, pm_id, net_pnl]``.
        pms: roster with ``[pm_id, payout_ratio, hurdle_rate, initial_hwm,
            pm_aum, loss_carryforward]``.
        Note: capital charge (hurdle_rate × pm_aum × dt) is already deducted
        from ``eligible_pnl`` by the cost engine, so no hurdle offset here.
        cfg: parsed config; reads ``cfg['comp_tiers']``.
        payout_ratio_override: if given, replaces every PM's BASE payout ratio
            (used by the dashboard sensitivity slider; tiers still add on top).

    Returns:
        Frame ``[date, pm_id, net_pnl, cum_net, hwm, hurdle_amt,
        loss_carryforward, profit_above, accrued_comp, daily_comp]``.
    """
    df = add_cumulative(pm_net_daily[["date", "pm_id", "eligible_pnl"]], "eligible_pnl", "pm_id", "cum_net")

    meta = pms.set_index("pm_id")
    cols = ["payout_ratio", "hurdle_rate", "initial_hwm", "pm_aum"]
    if "loss_carryforward" in meta.columns:
        cols.append("loss_carryforward")
    df = df.join(meta[cols], on="pm_id")
    if "loss_carryforward" not in df.columns:
        df["loss_carryforward"] = 0.0
    if payout_ratio_override is not None:
        df["payout_ratio"] = payout_ratio_override

    grp = df.groupby("pm_id", sort=False)
    # Day ordinal t = 1..n within each PM (time-scaled hurdle).
    df["t"] = grp.cumcount() + 1
    # hurdle_amt kept for audit display; capital charge already deducted in eligible_pnl.
    df["hurdle_amt"] = df["hurdle_rate"] * df["pm_aum"] * (df["t"] * DT)

    # Running high-water mark, floored at the initial HWM.
    df["hwm"] = grp["cum_net"].cummax()
    df["hwm"] = df[["hwm", "initial_hwm"]].max(axis=1)

    # Profit above HWM eligible for comp (capital charge already in eligible_pnl; no double-count).
    df["profit_above"] = (
        df["hwm"] - df["initial_hwm"] - df["loss_carryforward"]
    ).clip(lower=0)

    tiers = cfg.get("comp_tiers") or _FLAT_TIERS
    raw = tiered_comp(df["profit_above"], df["payout_ratio"], tiers)
    # Crystallization: comp never reverses -> running max enforces daily_comp >= 0.
    df["accrued_comp"] = raw.groupby(df["pm_id"]).cummax()
    df["daily_comp"] = df.groupby("pm_id", sort=False)["accrued_comp"].diff().fillna(
        df["accrued_comp"]
    )
    return df[
        [
            "date", "pm_id", "eligible_pnl", "cum_net", "hwm", "hurdle_amt",
            "loss_carryforward", "profit_above", "accrued_comp", "daily_comp",
        ]
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


def effective_payout_rates(payoff_daily: pd.DataFrame) -> pd.DataFrame:
    """Final comp, eligible profit, and the realized effective payout rate per PM.

    ``effective_payout_rate = total_comp / profit_above`` (NaN when no eligible
    profit). It sits between the base rate and base+top-tier add_pp.
    """
    last = (
        payoff_daily.sort_values("date")
        .groupby("pm_id", as_index=False)
        .last()[["pm_id", "accrued_comp", "profit_above"]]
        .rename(columns={"accrued_comp": "total_comp"})
    )
    last["effective_payout_rate"] = last["total_comp"] / last["profit_above"].where(
        last["profit_above"] > 0
    )
    return last


def fund_total_comp(payoff_daily: pd.DataFrame) -> float:
    """Fund-wide total comp expense = sum of every PM's final accrued comp."""
    return float(total_comp_by_pm(payoff_daily)["total_comp"].sum())
