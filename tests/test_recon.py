"""Reconciliation tie-outs R1–R7 (3-tier PnL: Gross/Net/Eligible)."""
from __future__ import annotations

import pandas as pd

from src.engine import economics, payoff, recon
from tests.conftest import pms_df


def _results(simple_cfg):
    pms = pms_df(simple_cfg)
    # center_daily for PM_A (cap=1000, AUM=2000, center=100bps*2000=20/yr, share 0.5): 10/252
    center_a = 10.0 / 252
    center_b = 10.0 / 252
    # capital_charge: hurdle_rate=0 for both PMs in simple_cfg → 0
    cc_a = cc_b = 0.0

    net_a = 100.0 - 10.0 - 5.0 - 5.0   # gross - financing - borrow - commission (trading costs only)
    net_b = -100.0 - 5.0 - 3.0 - 2.0

    # gross_pnl = trading_pnl + non_trading_pnl per row (120 = 100+20; -90 = -100+10).
    pm_net_daily = pd.DataFrame({
        "date":            pd.to_datetime(["2025-01-02", "2025-01-02"]),
        "pm_id":           ["PM_A", "PM_B"],
        "trading_pnl":     [100.0, -100.0],
        "non_trading_pnl": [20.0, 10.0],
        "gross_pnl":       [120.0, -90.0],
        "net_pnl":         [net_a, net_b],
        "eligible_pnl":    [net_a - center_a - cc_a, net_b - center_b - cc_b],
        "financing":       [10.0, 5.0],
        "borrow":          [5.0, 3.0],
        "commission":      [5.0, 2.0],
        "fx":              [0.0, 0.0],
        "center":          [center_a, center_b],
        "capital_charge":  [cc_a, cc_b],
    })
    payoff_daily = payoff.compute_payoff(pm_net_daily, pms, simple_cfg)
    total_comp  = payoff.fund_total_comp(payoff_daily)
    fund_trading         = float(pm_net_daily["trading_pnl"].sum())
    fund_non_trading     = float(pm_net_daily["non_trading_pnl"].sum())
    fund_gross           = float(pm_net_daily["gross_pnl"].sum())
    fund_net             = float(pm_net_daily["net_pnl"].sum())
    fund_eligible        = float(pm_net_daily["eligible_pnl"].sum())
    fund_capital_charges = float(pm_net_daily["capital_charge"].sum())  # 0.0 (hurdle_rate=0)
    econ = economics.investor_economics(fund_eligible, total_comp, simple_cfg, capital_charges=fund_capital_charges)
    return {
        "pm_net_daily":         pm_net_daily,
        "pms":                  pms,
        "payoff_daily":         payoff_daily,
        "fund_trading":         fund_trading,
        "fund_non_trading":     fund_non_trading,
        "position_trading":     fund_trading,      # bottom-up MTM ties by construction
        "income_total":         fund_non_trading,  # eod_income total ties by construction
        "fund_gross":           fund_gross,
        "fund_net":             fund_net,
        "fund_eligible_pnl":    fund_eligible,
        "fund_capital_charges": fund_capital_charges,
        "total_comp":           total_comp,
        "investor_net":         econ["investor_net"],
    }


def test_all_checks_pass(simple_cfg):
    checks = recon.run_checks(_results(simple_cfg), simple_cfg)
    assert recon.all_passed(checks), recon.to_frame(checks).to_string()


def test_broken_investor_net_fails(simple_cfg):
    results = _results(simple_cfg)
    results["investor_net"] += 1.0
    checks = recon.run_checks(results, simple_cfg)
    assert not recon.all_passed(checks)
    r4 = [c for c in checks if "Investor net" in c.name][0]
    assert not r4.passed
