"""Gross -> Net bridge costs: hand-verified, and PM Net excludes center cost."""
from __future__ import annotations

import pandas as pd

from src.engine import costs


def test_costs_and_net(simple_cfg):
    pm_daily = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "pm_id": ["PM_A"],
            "gross_pnl": [100.0],
            "gross_exposure": [1000.0],
            "short_notional": [500.0],
            "traded_notional": [200.0],
        }
    )
    out = costs.add_costs(pm_daily, simple_cfg).iloc[0]
    # financing = 0.252/252 * 1000 = 1.0
    assert round(out["financing"], 6) == 1.0
    # borrow = 0.504/252 * 500 = 1.0
    assert round(out["borrow"], 6) == 1.0
    # commission = 10bps * 200 = 0.001 * 200 = 0.2
    assert round(out["commission"], 6) == 0.2
    # total cost = 2.2 ; net = 100 - 2.2 = 97.8  (no center cost here)
    assert round(out["total_cost"], 6) == 2.2
    assert round(out["net_pnl"], 6) == 97.8


def test_pm_net_excludes_center_cost(simple_cfg):
    # PM net must depend only on trading costs, never on the fund overhead.
    pm_daily = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "pm_id": ["PM_A"],
            "gross_pnl": [100.0],
            "gross_exposure": [1000.0],
            "short_notional": [0.0],
            "traded_notional": [0.0],
        }
    )
    net = costs.add_costs(pm_daily, simple_cfg).iloc[0]["net_pnl"]
    # gross 100 - financing 1.0 only = 99.0 ; center cost (bps_on_aum) plays no part
    assert round(net, 6) == 99.0


def test_bridge_components_signs(simple_cfg):
    pm_daily = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "pm_id": ["PM_A"],
            "gross_pnl": [100.0],
            "gross_exposure": [1000.0],
            "short_notional": [0.0],
            "traded_notional": [0.0],
        }
    )
    net = costs.add_costs(pm_daily, simple_cfg)
    bridge = costs.bridge_components(net)
    assert bridge["Gross PnL"] == 100.0
    assert bridge["Financing"] < 0  # deductions are negative
    # gross + deductions == net
    recon = bridge["Gross PnL"] + bridge["Financing"] + bridge["Borrow"] + bridge["Commission"]
    assert round(recon, 6) == round(bridge["Net PnL"], 6)
