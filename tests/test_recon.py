"""Reconciliation tie-outs R1-R4."""
from __future__ import annotations

import pandas as pd

from src.engine import economics, payoff, recon


def _results(simple_cfg):
    pms = pd.DataFrame(simple_cfg["pms"])
    pm_net_daily = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "pm_id": ["PM_A", "PM_B"],
            "gross_pnl": [120.0, -90.0],
            "net_pnl": [100.0, -100.0],
            "financing": [10.0, 5.0],
            "borrow": [5.0, 3.0],
            "commission": [5.0, 2.0],
        }
    )
    payoff_daily = payoff.compute_payoff(pm_net_daily, pms)
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
    results["investor_net"] += 1.0  # tamper -> R4 (investor identity) must fail
    checks = recon.run_checks(results, simple_cfg)
    assert not recon.all_passed(checks)
    r4 = [c for c in checks if c.name.startswith("R4")][0]
    assert not r4.passed
