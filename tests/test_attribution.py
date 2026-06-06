"""Attribution and the netting-cost centerpiece."""
from __future__ import annotations

import pandas as pd

from src.engine import attribution, payoff
from tests.conftest import pms_df


def test_netting_cost_offsetting_pods(simple_cfg):
    # Pod A's PM makes +100, Pod B's PM loses -100 -> fund net = 0.
    daily = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "pm_id": ["PM_A", "PM_B"],
            "net_pnl": [100.0, -100.0],
        }
    )
    pms = pms_df(simple_cfg)
    payoff_daily = payoff.compute_payoff(daily, pms, simple_cfg)
    total_comp = payoff.fund_total_comp(payoff_daily)
    assert total_comp == 20.0  # only PM_A accrues: 0.2 * 100

    fund_net = 0.0
    # hypothetical netted comp = 0.2 * max(0, 0 - 0 - 0) = 0
    assert attribution.hypothetical_netted_comp(fund_net, simple_cfg) == 0.0
    # netting cost = max(0, 20 - 0) = 20
    assert attribution.netting_cost(total_comp, fund_net, simple_cfg) == 20.0


def test_netting_cost_zero_when_no_offset(simple_cfg):
    # Both PMs profitable; fund as one book would owe the same comp -> netting cost 0.
    daily = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "pm_id": ["PM_A", "PM_B"],
            "net_pnl": [100.0, 100.0],
        }
    )
    pms = pms_df(simple_cfg)
    total_comp = payoff.fund_total_comp(payoff.compute_payoff(daily, pms, simple_cfg))
    fund_net = 200.0
    assert total_comp == 40.0
    assert attribution.hypothetical_netted_comp(fund_net, simple_cfg) == 40.0
    assert attribution.netting_cost(total_comp, fund_net, simple_cfg) == 0.0


def test_cost_by_type():
    df = pd.DataFrame(
        {"financing": [1.0, 2.0], "borrow": [0.5, 0.5], "commission": [0.1, 0.1]}
    )
    out = attribution.cost_by_type(df).set_index("cost_type")["cost"]
    assert out["Financing"] == 3.0
    assert out["Borrow"] == 1.0
    assert round(out["Commission"], 6) == 0.2


def test_risk_return_includes_sharpe(simple_cfg):
    """risk_return now exposes sharpe = annual_return / annual_vol."""
    import numpy as np
    pms = pms_df(simple_cfg)
    n = 252
    dates = pd.date_range("2025-01-02", periods=n, freq="B")
    # PM_A: daily net = +0.5 (constant -> vol=0 -> sharpe NaN handled)
    # Use slight noise so vol > 0
    rng = np.random.default_rng(42)
    pm_a_net = 0.5 + rng.normal(0, 0.01, n)
    pm_b_net = -0.1 + rng.normal(0, 0.01, n)
    daily = pd.DataFrame({
        "date": list(dates) * 2,
        "pm_id": ["PM_A"] * n + ["PM_B"] * n,
        "net_pnl": list(pm_a_net) + list(pm_b_net),
    })
    rr = attribution.risk_return(daily, pms)
    assert "sharpe" in rr.columns
    # PM_A has positive return -> positive sharpe
    assert float(rr.loc[rr["pm_id"] == "PM_A", "sharpe"].iloc[0]) > 0
    # PM_B has negative return -> negative sharpe
    assert float(rr.loc[rr["pm_id"] == "PM_B", "sharpe"].iloc[0]) < 0
