"""Gross -> Net bridge costs: now includes FX + center pass-through."""
from __future__ import annotations

import pandas as pd

from src.engine import costs


def _pms_df(simple_cfg):
    return pd.DataFrame(simple_cfg["pms"])


def _pm_daily(pm_id="PM_A", gross_pnl=100.0, gross_exposure=1000.0,
              short_notional=500.0, traded_notional=200.0, fx_notional=0.0):
    return pd.DataFrame({
        "date": pd.to_datetime(["2025-01-02"]),
        "pm_id": [pm_id],
        "gross_pnl": [gross_pnl],
        "gross_exposure": [gross_exposure],
        "short_notional": [short_notional],
        "traded_notional": [traded_notional],
        "fx_notional": [fx_notional],
    })


def test_costs_and_net(simple_cfg):
    """Hand-verify each cost line and pm_net = gross - sum(costs)."""
    out = costs.add_costs(_pm_daily(), simple_cfg, _pms_df(simple_cfg)).iloc[0]
    # financing = 0.252/252 * 1000 = 1.0
    assert round(out["financing"], 6) == 1.0
    # borrow = 0.504/252 * 500 = 1.0
    assert round(out["borrow"], 6) == 1.0
    # commission = 10bps * 200 = 0.2
    assert round(out["commission"], 6) == 0.2
    # fx = 0 (no fx_rate in simple_cfg, and fx_notional=0)
    assert round(out.get("fx", 0.0), 6) == 0.0
    # center for PM_A: AUM=2000, center=100bps*2000=20/year; 1/252 per day = 20/252
    # PM_A cap=1000, share=0.5 -> center_daily = 10/252 ~ 0.039683
    expected_center = 10.0 / 252
    assert abs(out["center"] - expected_center) < 1e-6
    # net = gross - financing - borrow - commission - fx - center
    expected_net = 100.0 - 1.0 - 1.0 - 0.2 - 0.0 - expected_center
    assert abs(out["net_pnl"] - expected_net) < 1e-6


def test_center_cost_pass_through_in_pm_net(simple_cfg):
    """Center cost is now a pass-through inside pm_net (not excluded)."""
    out = costs.add_costs(_pm_daily(short_notional=0, traded_notional=0), simple_cfg, _pms_df(simple_cfg)).iloc[0]
    # financing only + center; net < gross - financing
    center_daily = 10.0 / 252
    expected_net = 100.0 - 1.0 - center_daily
    assert abs(out["net_pnl"] - expected_net) < 1e-6


def test_fx_cost_only_on_fx_assets(simple_cfg):
    """FX rate charges fx_notional, not gross_exposure."""
    cfg = dict(simple_cfg, costs=dict(simple_cfg["costs"], fx_rate=0.252))
    # fx_notional=200 -> fx = 0.252/252 * 200 = 0.2
    out = costs.add_costs(
        _pm_daily(short_notional=0, traded_notional=0, fx_notional=200.0),
        cfg, _pms_df(simple_cfg)
    ).iloc[0]
    assert abs(out["fx"] - 0.2) < 1e-6


def test_bridge_components_signs(simple_cfg):
    """All deductions are negative; sum of components ties to PM Net."""
    pm_net = costs.add_costs(
        _pm_daily(short_notional=0, traded_notional=0), simple_cfg, _pms_df(simple_cfg)
    )
    bridge = costs.bridge_components(pm_net)
    assert bridge["Gross PnL"] == 100.0
    assert bridge["Financing"] < 0
    total = (bridge["Gross PnL"] + bridge["Financing"] + bridge["Borrow"]
             + bridge["Commission"] + bridge["FX"] + bridge["Center"])
    assert abs(total - bridge["PM Net"]) < 1e-6
