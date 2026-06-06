"""Reconciliation tie-outs R1–R7 (center is now pass-through)."""
from __future__ import annotations

import pandas as pd

from src.engine import economics, payoff, recon
from tests.conftest import pms_df


def _results(simple_cfg):
    pms = pms_df(simple_cfg)
    # center daily for PM_A (cap=1000, AUM=2000): annual=20, daily=20/252, split 50% -> 10/252
    center_a = 10.0 / 252
    center_b = 10.0 / 252
    pm_net_daily = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-02"]),
            "pm_id": ["PM_A", "PM_B"],
            "gross_pnl": [120.0, -90.0],
            "net_pnl": [100.0 - center_a, -100.0 - center_b],  # center inside net
            "financing": [10.0, 5.0],
            "borrow": [5.0, 3.0],
            "commission": [5.0, 2.0],
            "fx": [0.0, 0.0],
            "center": [center_a, center_b],
        }
    )
    payoff_daily = payoff.compute_payoff(pm_net_daily, pms, simple_cfg)
    total_comp = payoff.fund_total_comp(payoff_daily)
    fund_gross = float(pm_net_daily["gross_pnl"].sum())
    fund_net = float(pm_net_daily["net_pnl"].sum())
    econ = economics.investor_economics(fund_net, total_comp, simple_cfg)
    return {
        "pm_net_daily": pm_net_daily,
        "pms": pms,
        "payoff_daily": payoff_daily,
        "fund_gross": fund_gross,
        "fund_net": fund_net,
        "total_comp": total_comp,
        "investor_net": econ["investor_net"],
    }


def test_all_checks_pass(simple_cfg):
    checks = recon.run_checks(_results(simple_cfg), simple_cfg)
    assert recon.all_passed(checks), recon.to_frame(checks).to_string()


def test_broken_investor_net_fails(simple_cfg):
    results = _results(simple_cfg)
    results["investor_net"] += 1.0  # tamper -> R4 must fail
    checks = recon.run_checks(results, simple_cfg)
    assert not recon.all_passed(checks)
    r4 = [c for c in checks if "Investor net" in c.name][0]
    assert not r4.passed
