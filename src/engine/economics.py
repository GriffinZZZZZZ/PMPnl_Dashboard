"""Investor net economics — the fund-level waterfall LPs actually keep.

Center cost is a **fund-level overhead** accrued daily (* dt) and deducted once
here (never inside PM Net), so the reconciliation identities stay exact::

    fund_net_pnl       = sum_pm pm_net
    center_cost_annual = center_cost_bps/1e4 * AUM
    center_cost_total  = center_cost_annual * (n_business_days * dt)   (accrued over time)
    investor_net       = fund_net_pnl - total_comp - center_cost_total
    comp_expense_ratio = total_comp / fund_net_pnl
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
    """Allocate total center cost to PMs pro-rata by capital (FOR DISPLAY ONLY)."""
    total = center_cost_total(cfg)
    cap = pms["allocated_capital"]
    out = pms[["pm_id"]].copy()
    out["center_cost_alloc"] = total * cap / cap.sum()
    return out


def investor_economics(fund_net: float, total_comp: float, cfg: dict) -> dict:
    """Bundle the fund-to-investor waterfall into one dict for the UI/recon."""
    cc = center_cost_total(cfg)
    investor_net = fund_net - total_comp - cc
    # Comp expense ratio is only meaningful when the fund made money.
    comp_ratio = total_comp / fund_net if fund_net > _EPS else float("nan")
    return {
        "aum": aum(cfg),
        "fund_net": fund_net,
        "total_comp": total_comp,
        "center_cost": cc,
        "investor_net": investor_net,
        "comp_expense_ratio": comp_ratio,
    }
