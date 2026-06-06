"""Investor net economics — the fund-level waterfall LPs actually keep.

Capital charge is a hard deduction from each PM's eligible PnL (lowers the comp base)
but is a pass-through from PM books to the fund pool, which flows back to investors::

    fund_eligible_pnl    = sum_pm eligible_pnl     (after trading costs, center, capital charge)
    fund_capital_charges = sum_pm capital_charge    (pass-through: PM → fund pool → investor)
    investor_net         = fund_eligible_pnl - mgmt_fee - base_comp - total_comp + fund_capital_charges
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


def base_comp_total(cfg: dict) -> float:
    """Total base compensation accrued over the simulated period (Σ base_salary × period_fraction)."""
    pf = period_fraction(cfg)
    return sum(pm.get("base_salary", 0.0) for pm in cfg["pms"]) * pf


def management_fee_total(cfg: dict) -> float:
    """Management fee charged to investors (the '2' in '2-and-20'). Annual bps on AUM × period."""
    mf = cfg.get("management_fee", {})
    return mf.get("bps_on_aum", 0.0) / 1e4 * aum(cfg) * period_fraction(cfg)


def investor_economics(
    fund_eligible: float,
    total_comp: float,
    cfg: dict,
    capital_charges: float = 0.0,
    base_comp: float = 0.0,
    mgmt_fee: float = 0.0,
) -> dict:
    """Fund-to-investor waterfall.

    ``fund_eligible``   = sum of PM eligible PnL (after trading costs, center, capital charge).
    ``capital_charges`` = sum of capital charges deducted from PM books; flow back to investors.
    ``base_comp``       = total fixed PM salary accrued this period (fund-level cost).
    ``mgmt_fee``        = management fee charged on AUM (the '2' in '2-and-20').

    Investor net = fund_eligible - mgmt_fee - base_comp - incentive_comp + capital_charges.
    """
    investor_net = fund_eligible - mgmt_fee - base_comp - total_comp + capital_charges
    comp_ratio = total_comp / fund_eligible if fund_eligible > _EPS else float("nan")
    cc = center_cost_total(cfg)
    return {
        "aum": aum(cfg),
        "fund_eligible": fund_eligible,
        "capital_charges": capital_charges,
        "base_comp": base_comp,
        "mgmt_fee": mgmt_fee,
        "total_comp": total_comp,
        "center_cost": cc,
        "investor_net": investor_net,
        "comp_expense_ratio": comp_ratio,
    }
