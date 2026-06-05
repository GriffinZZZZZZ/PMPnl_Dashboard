"""Investor net economics and center-cost treatment."""
from __future__ import annotations

import pandas as pd

from src.engine import economics


def test_center_cost_and_investor_net(simple_cfg):
    # AUM = 2000 ; center cost = 100bps * 2000 * period_fraction(1.0) = 20
    assert economics.aum(simple_cfg) == 2000.0
    assert economics.period_fraction(simple_cfg) == 1.0
    assert economics.center_cost_total(simple_cfg) == 20.0

    econ = economics.investor_economics(fund_net=500.0, total_comp=80.0, cfg=simple_cfg)
    # investor net = 500 - 80 - 20 = 400
    assert econ["investor_net"] == 400.0
    # comp expense ratio = 80 / 500 = 0.16
    assert round(econ["comp_expense_ratio"], 6) == 0.16


def test_center_cost_accrues_over_partial_period(simple_cfg):
    # Half a year should accrue half the annual center cost.
    cfg = dict(simple_cfg, n_business_days=126)
    assert economics.period_fraction(cfg) == 0.5
    assert economics.center_cost_total(cfg) == 10.0


def test_center_cost_allocation_prorata(simple_cfg):
    pms = pd.DataFrame(simple_cfg["pms"])
    alloc = economics.allocate_center_cost(simple_cfg, pms)
    # equal capital -> 20 split evenly = 10 each
    assert sorted(alloc["center_cost_alloc"].round(6)) == [10.0, 10.0]
    assert round(alloc["center_cost_alloc"].sum(), 6) == economics.center_cost_total(simple_cfg)
