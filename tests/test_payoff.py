"""High-water-mark comp crystallization: ratcheting, time-scaled hurdle, no clawback."""
from __future__ import annotations

import pandas as pd

from src.engine import payoff


def _pms(payout_ratio=0.2, hurdle_rate=0.0, initial_hwm=0, cap=1000):
    return pd.DataFrame(
        [{"pm_id": "P", "pod_id": "X", "name": "n", "allocated_capital": cap,
          "payout_ratio": payout_ratio, "hurdle_rate": hurdle_rate, "initial_HWM": initial_hwm}]
    )


def _daily(net_list):
    dates = pd.date_range("2024-01-01", periods=len(net_list), freq="D")
    return pd.DataFrame({"date": dates, "pm_id": "P", "net_pnl": net_list})


def test_no_clawback_ratchet():
    # cum_net = [50, 100, 70]; peak = [50, 100, 100]; payout 0.2, hurdle 0
    out = payoff.compute_payoff(_daily([50, 50, -30]), _pms())
    assert list(out["accrued_comp"]) == [10.0, 20.0, 20.0]  # stays 20 despite day-3 drawdown
    assert list(out["daily_comp"]) == [10.0, 10.0, 0.0]      # daily comp never negative


def test_time_scaled_hurdle_and_crystallization():
    # hurdle_rate*cap = 2.52*1000 = 2520 ; hurdle_amt_t = 2520 * t/252 = 10*t -> [10,20,30]
    out = payoff.compute_payoff(_daily([50, 50, -30]), _pms(hurdle_rate=2.52))
    # raw = 0.2*max(0, peak - hurdle_amt) = [0.2*40, 0.2*80, 0.2*70] = [8,16,14]
    # crystallized (running max) -> [8, 16, 16]
    assert list(out["accrued_comp"]) == [8.0, 16.0, 16.0]


def test_underwater_pm_earns_zero_comp():
    out = payoff.compute_payoff(_daily([-10, -20, 5]), _pms())
    # cum stays below initial HWM 0 -> peak 0 -> no comp ever
    assert list(out["accrued_comp"]) == [0.0, 0.0, 0.0]
    assert payoff.fund_total_comp(out) == 0.0


def test_override_changes_comp():
    base = payoff.fund_total_comp(payoff.compute_payoff(_daily([100]), _pms()))
    doubled = payoff.fund_total_comp(
        payoff.compute_payoff(_daily([100]), _pms(), payout_ratio_override=0.4)
    )
    assert base == 20.0 and doubled == 40.0
