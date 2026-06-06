"""Investor net economics — the fund-level waterfall LPs actually keep.

Center cost is now a **pass-through** allocated to each PM daily and included in
``pm_net``. So the investor waterfall simplifies to::

    fund_net_pnl       = sum_pm pm_net          (center already deducted)
    investor_net       = fund_net_pnl - total_comp
    comp_expense_ratio = total_comp / fund_net_pnl

The center total is still tracked for reporting and reconciliation (R7).
"""
from __future__ import annotations

import pandas as pd

TRADING_DAYS = 252
DT = 1.0 / TRADING_DAYS
_EPS = 1e-9


def aum(cfg: dict) -> float:
    """Assets under management = sum of pod allocated capital (fund capital)."""
    return float(sum(p["allocated_capital"] for p in cfg["pods"]))


def period_fraction(cfg: dict) -> float:
    """Fraction of a year covered = n_business_days * dt (1.0 for a full 252d year)."""
    return cfg.get("n_business_days", TRADING_DAYS) * DT


def center_cost_annual(cfg: dict) -> float:
    """Annual center cost in dollars (bps on AUM)."""
    return cfg["center_cost"]["bps_on_aum"] / 1e4 * aum(cfg)


def center_cost_total(cfg: dict) -> float:
    """Center cost accrued over the simulated period (annual * period fraction)."""
    return center_cost_annual(cfg) * period_fraction(cfg)


def allocate_center_cost(cfg: dict, pms: pd.DataFrame) -> pd.DataFrame:
    """Per-PM center cost allocation by AUM share (pass-through, not display-only)."""
    total = center_cost_total(cfg)
    cap = pms["pm_aum"]
    out = pms[["pm_id", "pm_aum"]].copy()
    out["center_cost_alloc"] = total * cap / cap.sum()
    return out


def investor_economics(fund_eligible: float, total_comp: float, cfg: dict) -> dict:
    """Fund-to-investor waterfall.

    ``fund_eligible`` = fund net PnL after trading costs, center, and capital charges.
    Investor receives ``fund_eligible - total_comp``.
    """
    investor_net = fund_eligible - total_comp
    comp_ratio = total_comp / fund_eligible if fund_eligible > _EPS else float("nan")
    # Keep center_cost for reporting / R7 reconciliation.
    cc = center_cost_total(cfg)
    return {
        "aum": aum(cfg),
        "fund_eligible": fund_eligible,
        "total_comp": total_comp,
        "center_cost": cc,
        "investor_net": investor_net,
        "comp_expense_ratio": comp_ratio,
    }
