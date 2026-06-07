"""HWM comp crystallization: ratchet, loss carryforward, tiered schedule.

Capital charge (hurdle_rate × pm_aum × dt) is now deducted in costs.py as part
of eligible_pnl. payoff.compute_payoff receives eligible_pnl directly and does
NOT subtract hurdle_amt from profit_above (no double-count).
hurdle_amt is still computed and stored for audit display.
"""
from __future__ import annotations

import pandas as pd

from src.engine import payoff

FLAT: dict = {}
TIERED = {
    "comp_tiers": [
        {"upto": 1_000_000, "add_pp": 0.00},
        {"upto": 2_000_000, "add_pp": 0.03},
        {"upto": None, "add_pp": 0.06},
    ]
}


def _pms(payout_ratio=0.2, hurdle_rate=0.0, initial_hwm=0, cap=1000, loss_carryforward=0):
    return pd.DataFrame(
        [{"pm_id": "P", "pod_id": "X", "pm_name": "n", "pm_aum": cap,
          "payout_ratio": payout_ratio, "hurdle_rate": hurdle_rate,
          "initial_hwm": initial_hwm, "loss_carryforward": loss_carryforward}]
    )


def _daily(eligible_list):
    """Build a pm_net_daily-like frame with eligible_pnl column."""
    dates = pd.date_range("2025-01-01", periods=len(eligible_list), freq="D")
    return pd.DataFrame({"date": dates, "pm_id": "P", "eligible_pnl": eligible_list})


def test_no_clawback_ratchet():
    # cum_eligible = [50, 100, 70]; peak = [50, 100, 100]; payout 0.2
    out = payoff.compute_payoff(_daily([50, 50, -30]), _pms(), FLAT)
    assert list(out["accrued_comp"]) == [10.0, 20.0, 20.0]
    assert list(out["daily_comp"]) == [10.0, 10.0, 0.0]


def test_hurdle_amt_computed_for_audit_but_not_in_profit_above():
    """hurdle_amt column exists (for display), but profit_above ignores it.

    Capital charge is already deducted from eligible_pnl in costs.py, so
    profit_above = peak_cum_eligible - initial_hwm - loss_carryforward (no hurdle offset).
    Daily eligible changes: +40, +40, -10 → cumsum [40, 80, 70] → peak [40, 80, 80].
    """
    out = payoff.compute_payoff(_daily([40, 40, -10]), _pms(hurdle_rate=2.52), FLAT)
    # accrued_comp = 0.2 * [40, 80, 80] crystallized → [8, 16, 16]
    assert list(out["accrued_comp"]) == [8.0, 16.0, 16.0]
    assert "hurdle_amt" in out.columns


def test_underwater_pm_earns_zero_comp():
    out = payoff.compute_payoff(_daily([-10, -20, 5]), _pms(), FLAT)
    assert list(out["accrued_comp"]) == [0.0, 0.0, 0.0]
    assert payoff.fund_total_comp(out) == 0.0


def test_override_changes_comp():
    base = payoff.fund_total_comp(payoff.compute_payoff(_daily([100]), _pms(), FLAT))
    doubled = payoff.fund_total_comp(
        payoff.compute_payoff(_daily([100]), _pms(), FLAT, payout_ratio_override=0.4)
    )
    assert base == 20.0 and doubled == 40.0


def test_tiered_schedule_marginal_rates():
    out = payoff.compute_payoff(_daily([3_000_000]), _pms(), TIERED)
    assert out["accrued_comp"].iloc[-1] == 690_000.0
    eff = payoff.effective_payout_rates(out)["effective_payout_rate"].iloc[0]
    assert 0.2 < eff < 0.26


def test_loss_carryforward_must_be_recovered_first():
    out = payoff.compute_payoff(_daily([300_000, 300_000]), _pms(loss_carryforward=500_000), TIERED)
    assert list(out["accrued_comp"]) == [0.0, 20_000.0]
