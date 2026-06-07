"""Investor net economics — center is now pass-through inside fund_net."""
from __future__ import annotations

import pandas as pd

from src.engine import economics
from tests.conftest import pms_df


def test_investor_net_is_fund_eligible_minus_comp(simple_cfg):
    """investor_net = fund_eligible_pnl - total_comp (base_comp=0, mgmt_fee=0 by default)."""
    econ = economics.investor_economics(500.0, total_comp=80.0, cfg=simple_cfg)
    assert econ["investor_net"] == 420.0
    assert round(econ["comp_expense_ratio"], 6) == round(80 / 500, 6)


def test_investor_net_includes_base_comp_and_mgmt_fee(simple_cfg):
    """investor_net = eligible - mgmt_fee - base_comp - incentive_comp + capital_charges."""
    econ = economics.investor_economics(
        500.0, total_comp=80.0, cfg=simple_cfg,
        capital_charges=10.0, base_comp=30.0, mgmt_fee=20.0,
    )
    # 500 - 20 - 30 - 80 + 10 = 380
    assert econ["investor_net"] == 380.0
    assert econ["base_comp"] == 30.0
    assert econ["mgmt_fee"] == 20.0


def test_base_comp_total_no_salary(simple_cfg):
    """simple_cfg has no base_salary → base_comp_total == 0."""
    assert economics.base_comp_total(simple_cfg) == 0.0


def test_base_comp_total_with_salary():
    """base_comp_total = sum(base_salary) × period_fraction."""
    import copy
    cfg = {
        "n_business_days": 252,
        "pods": [{"allocated_capital": 1000}],
        "center_cost": {"bps_on_aum": 0},
        "pms": [
            {"pm_id": "A", "base_salary": 500000},
            {"pm_id": "B", "base_salary": 300000},
        ],
    }
    # period_fraction = 252/252 = 1.0
    assert economics.base_comp_total(cfg) == 800000.0


def test_management_fee_no_config(simple_cfg):
    """simple_cfg has no management_fee block → fee == 0."""
    assert economics.management_fee_total(simple_cfg) == 0.0


def test_management_fee_2pct():
    """management_fee = 2% × AUM × period_fraction."""
    cfg = {
        "n_business_days": 252,
        "pods": [{"allocated_capital": 100_000_000}],
        "center_cost": {"bps_on_aum": 0},
        "pms": [],
        "management_fee": {"bps_on_aum": 200},
    }
    # 2% × 100M × 1.0 = 2M
    assert economics.management_fee_total(cfg) == 2_000_000.0


def test_center_cost_total_still_computable(simple_cfg):
    """center_cost_total is still computed for reporting / R7."""
    assert economics.aum(simple_cfg) == 2000.0
    assert economics.period_fraction(simple_cfg) == 1.0
    assert economics.center_cost_total(simple_cfg) == 20.0


def test_center_cost_accrues_over_partial_period(simple_cfg):
    cfg = dict(simple_cfg, n_business_days=126)
    assert economics.period_fraction(cfg) == 0.5
    assert economics.center_cost_total(cfg) == 10.0


def test_center_cost_allocation_prorata(simple_cfg):
    pms = pms_df(simple_cfg)
    alloc = economics.allocate_center_cost(simple_cfg, pms)
    # equal capital -> 20 split evenly = 10 each
    assert sorted(alloc["center_cost_alloc"].round(6)) == [10.0, 10.0]
    assert round(alloc["center_cost_alloc"].sum(), 6) == economics.center_cost_total(simple_cfg)
