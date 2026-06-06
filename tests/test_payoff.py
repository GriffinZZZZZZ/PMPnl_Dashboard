"""HWM comp crystallization: ratchet, hurdle, tiered schedule, loss carryforward."""
from __future__ import annotations

import pandas as pd

from src.engine import payoff

# Flat schedule (single base tier) reproduces the original hand calcs.
FLAT: dict = {}
# Structural ladder: base on first $1M, +3pp on $1M–$2M, +6pp above $2M.
TIERED = {
    "comp_tiers": [
        {"upto": 1_000_000, "add_pp": 0.00},
        {"upto": 2_000_000, "add_pp": 0.03},
        {"upto": None, "add_pp": 0.06},
    ]
}


def _pms(payout_ratio=0.2, hurdle_rate=0.0, initial_hwm=0, cap=1000, prior_year_pnl=0):
    return pd.DataFrame(
        [{"pm_id": "P", "pod_id": "X", "name": "n", "allocated_capital": cap,
          "payout_ratio": payout_ratio, "hurdle_rate": hurdle_rate,
          "initial_HWM": initial_hwm, "prior_year_pnl": prior_year_pnl}]
    )


def _daily(net_list):
    dates = pd.date_range("2025-01-01", periods=len(net_list), freq="D")
    return pd.DataFrame({"date": dates, "pm_id": "P", "net_pnl": net_list})


def test_no_clawback_ratchet():
    # cum_net = [50, 100, 70]; peak = [50, 100, 100]; payout 0.2, hurdle 0
    out = payoff.compute_payoff(_daily([50, 50, -30]), _pms(), FLAT)
    assert list(out["accrued_comp"]) == [10.0, 20.0, 20.0]  # stays 20 despite day-3 drawdown
    assert list(out["daily_comp"]) == [10.0, 10.0, 0.0]      # daily comp never negative


def test_time_scaled_hurdle_and_crystallization():
    # hurdle_rate*cap = 2.52*1000 = 2520 ; hurdle_amt_t = 2520 * t/252 = 10*t -> [10,20,30]
    out = payoff.compute_payoff(_daily([50, 50, -30]), _pms(hurdle_rate=2.52), FLAT)
    # raw = 0.2*max(0, peak - hurdle_amt) = [0.2*40, 0.2*80, 0.2*70] = [8,16,14]
    # crystallized (running max) -> [8, 16, 16]
    assert list(out["accrued_comp"]) == [8.0, 16.0, 16.0]


def test_underwater_pm_earns_zero_comp():
    out = payoff.compute_payoff(_daily([-10, -20, 5]), _pms(), FLAT)
    # cum stays below initial HWM 0 -> peak 0 -> no comp ever
    assert list(out["accrued_comp"]) == [0.0, 0.0, 0.0]
    assert payoff.fund_total_comp(out) == 0.0


def test_override_changes_comp():
    base = payoff.fund_total_comp(payoff.compute_payoff(_daily([100]), _pms(), FLAT))
    doubled = payoff.fund_total_comp(
        payoff.compute_payoff(_daily([100]), _pms(), FLAT, payout_ratio_override=0.4)
    )
    assert base == 20.0 and doubled == 40.0


def test_tiered_schedule_marginal_rates():
    # Profit above HWM = $3M in one day. base 0.2.
    # tier0: 0.20 * 1M = 200,000 ; tier1: 0.23 * 1M = 230,000 ; tier2: 0.26 * 1M = 260,000
    out = payoff.compute_payoff(_daily([3_000_000]), _pms(), TIERED)
    assert out["accrued_comp"].iloc[-1] == 690_000.0
    # Effective rate sits between base and base + top add_pp.
    eff = payoff.effective_payout_rates(out)["effective_payout_rate"].iloc[0]
    assert 0.2 < eff < 0.26


def test_loss_carryforward_must_be_recovered_first():
    # Prior-year loss 500k must be earned back before comp accrues.
    out = payoff.compute_payoff(_daily([300_000, 300_000]), _pms(prior_year_pnl=-500_000), TIERED)
    # cum [300k, 600k]; profit_above = max(0, peak - 500k) = [0, 100k]
    assert list(out["accrued_comp"]) == [0.0, 20_000.0]  # 0 until recovered, then 0.2 * 100k
