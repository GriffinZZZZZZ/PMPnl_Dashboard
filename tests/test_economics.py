"""Investor net economics — center is now pass-through inside fund_net."""
from __future__ import annotations

import pandas as pd

from src.engine import economics


def test_investor_net_is_fund_net_minus_comp(simple_cfg):
    """With center as pass-through, investor_net = fund_net - total_comp."""
    econ = economics.investor_economics(fund_net=500.0, total_comp=80.0, cfg=simple_cfg)
    # investor net = 500 - 80 = 420 (center already deducted in fund_net)
    assert econ["investor_net"] == 420.0
    assert round(econ["comp_expense_ratio"], 6) == round(80 / 500, 6)


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
    pms = pd.DataFrame(simple_cfg["pms"])
    alloc = economics.allocate_center_cost(simple_cfg, pms)
    # equal capital -> 20 split evenly = 10 each
    assert sorted(alloc["center_cost_alloc"].round(6)) == [10.0, 10.0]
    assert round(alloc["center_cost_alloc"].sum(), 6) == economics.center_cost_total(simple_cfg)
