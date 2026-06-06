"""Investor net economics — the fund-level waterfall LPs actually keep.

Capital charge is a hard deduction from each PM's eligible PnL (lowers the comp base)
but is a pass-through from PM books to the fund pool, which flows back to investors::

    fund_eligible_pnl    = sum_pm eligible_pnl     (after trading costs, center, capital charge)
    fund_capital_charges = sum_pm capital_charge    (pass-through: PM → fund pool → investor)
    investor_net         = fund_eligible_pnl - total_comp + fund_capital_charges
                         = fund_net_pnl - center_cost - total_comp
    comp_expense_ratio   = total_comp / fund_eligible_pnl

Center cost is tracked for reporting and reconciliation (R7).
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


def investor_economics(
    fund_eligible: float,
    total_comp: float,
    cfg: dict,
    capital_charges: float = 0.0,
) -> dict:
    """Fund-to-investor waterfall.

    ``fund_eligible``   = sum of PM eligible PnL (after trading costs, center, capital charge).
    ``capital_charges`` = sum of capital charges deducted from PM books; these flow back to
                          the investor pool, so they are added back here.
    Investor net = fund_eligible - comp + capital_charges = fund_net - center - comp.
    """
    investor_net = fund_eligible - total_comp + capital_charges
    comp_ratio = total_comp / fund_eligible if fund_eligible > _EPS else float("nan")
    cc = center_cost_total(cfg)
    return {
        "aum": aum(cfg),
        "fund_eligible": fund_eligible,
        "capital_charges": capital_charges,
        "total_comp": total_comp,
        "center_cost": cc,
        "investor_net": investor_net,
        "comp_expense_ratio": comp_ratio,
    }
