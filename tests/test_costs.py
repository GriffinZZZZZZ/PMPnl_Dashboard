"""Gross → Net → Eligible PnL: three-tier cost bridge."""
from __future__ import annotations

import pandas as pd

from src.engine import costs
from tests.conftest import pms_df as _pms_df


def _pm_daily(pm_id="PM_A", trading_pnl=100.0, non_trading_pnl=0.0,
              gross_exposure=1000.0, long_notional=1000.0,
              short_notional=500.0, traded_notional=200.0, fx_notional=0.0):
    return pd.DataFrame({
        "date":             pd.to_datetime(["2025-01-02"]),
        "pm_id":            [pm_id],
        "trading_pnl":      [trading_pnl],
        "non_trading_pnl":  [non_trading_pnl],
        "gross_exposure":   [gross_exposure],
        "long_notional":    [long_notional],
        "short_notional":   [short_notional],
        "traded_notional":  [traded_notional],
        "fx_notional":      [fx_notional],
    })


def test_trading_costs_and_net_pnl(simple_cfg):
    """net_pnl = gross - trading costs only (financing+borrow+commission+fx); no center."""
    out = costs.add_costs(_pm_daily(), simple_cfg, _pms_df(simple_cfg)).iloc[0]
    # financing = 0.252/252 * long_notional(1000) = 1.0  (longs only — NOT gross exposure)
    assert round(out["financing"], 6) == 1.0
    # borrow = 0.504/252 * 500 = 1.0
    assert round(out["borrow"], 6) == 1.0
    # commission = 10bps * 200 = 0.2
    assert round(out["commission"], 6) == 0.2
    # fx = 0 (no fx_rate in simple_cfg)
    assert round(out.get("fx", 0.0), 6) == 0.0
    # net_pnl = gross - trading costs (NO center)
    expected_net = 100.0 - 1.0 - 1.0 - 0.2 - 0.0
    assert abs(out["net_pnl"] - expected_net) < 1e-6


def test_financing_charges_longs_only(simple_cfg):
    """Financing is on long_notional only; shorts pay borrow, not financing (no double-charge)."""
    # long_notional=0 → financing must be 0 even though short_notional > 0.
    out = costs.add_costs(_pm_daily(long_notional=0.0, short_notional=500.0),
                          simple_cfg, _pms_df(simple_cfg)).iloc[0]
    assert round(out["financing"], 6) == 0.0
    assert round(out["borrow"], 6) == 1.0   # shorts still pay borrow


def test_gross_is_trading_plus_non_trading(simple_cfg):
    """gross_pnl = trading_pnl + non_trading_pnl; net/eligible inherit the non-trading income."""
    out = costs.add_costs(_pm_daily(trading_pnl=100.0, non_trading_pnl=30.0),
                          simple_cfg, _pms_df(simple_cfg)).iloc[0]
    assert abs(out["gross_pnl"] - 130.0) < 1e-9
    # net = gross - trading costs (1+1+0.2) = 130 - 2.2
    assert abs(out["net_pnl"] - (130.0 - 2.2)) < 1e-6


def test_eligible_pnl_deducts_overhead(simple_cfg):
    """eligible_pnl = net_pnl - center - capital_charge."""
    out = costs.add_costs(_pm_daily(), simple_cfg, _pms_df(simple_cfg)).iloc[0]
    # center for PM_A: AUM=2000, center=100bps*2000=20/year; PM_A share=0.5 -> 10/252
    expected_center = 10.0 / 252
    assert abs(out["center"] - expected_center) < 1e-6
    # capital_charge: hurdle_rate=0 in simple_cfg -> 0
    assert abs(out["capital_charge"], ) < 1e-9
    expected_net = 100.0 - 1.0 - 1.0 - 0.2
    expected_eligible = expected_net - expected_center - 0.0
    assert abs(out["eligible_pnl"] - expected_eligible) < 1e-6


def test_capital_charge_with_nonzero_hurdle(simple_cfg):
    """capital_charge = hurdle_rate × pm_aum × dt per day."""
    from tests.conftest import pms_df
    import copy
    cfg = copy.deepcopy(simple_cfg)
    # give PM_A a 5% hurdle
    cfg["pms"][0]["hurdle_rate"] = 0.252  # 0.252/252 = 0.001 daily on 1000 capital
    pms = pms_df(cfg)
    out = costs.add_costs(_pm_daily(), cfg, pms).iloc[0]
    expected_cc = 0.252 * 1000 * (1.0 / 252)  # = 1.0
    assert abs(out["capital_charge"] - expected_cc) < 1e-6
    # eligible = net - center - capital_charge
    expected_center = 10.0 / 252
    expected_net = 100.0 - 1.0 - 1.0 - 0.2
    assert abs(out["eligible_pnl"] - (expected_net - expected_center - expected_cc)) < 1e-6


def test_fx_cost_only_on_fx_assets(simple_cfg):
    """FX rate charges fx_notional, not gross_exposure."""
    cfg = dict(simple_cfg, costs=dict(simple_cfg["costs"], fx_rate=0.252))
    out = costs.add_costs(
        _pm_daily(short_notional=0, traded_notional=0, fx_notional=200.0),
        cfg, _pms_df(simple_cfg)
    ).iloc[0]
    assert abs(out["fx"] - 0.2) < 1e-6


def test_capital_charge_uses_pm_aum_column(simple_cfg):
    """When pm_aum column is present, capital_charge scales with it (time-varying path)."""
    from tests.conftest import pms_df
    import copy
    cfg = copy.deepcopy(simple_cfg)
    cfg["pms"][0]["hurdle_rate"] = 0.252   # 0.252/252 = 0.001/day per unit of AUM
    pms = pms_df(cfg)
    # Two rows: same PM, different pm_aum values
    df = pd.DataFrame({
        "date":           pd.to_datetime(["2025-01-02", "2025-01-03"]),
        "pm_id":          ["PM_A", "PM_A"],
        "trading_pnl":    [100.0, 100.0],
        "non_trading_pnl":[0.0, 0.0],
        "gross_exposure": [1000.0, 2000.0],
        "long_notional":  [1000.0, 2000.0],
        "short_notional": [0.0, 0.0],
        "traded_notional":[0.0, 0.0],
        "fx_notional":    [0.0, 0.0],
        "pm_aum":         [1000.0, 2000.0],   # time-varying
    })
    out = costs.add_costs(df, cfg, pms)
    cc = out["capital_charge"].tolist()
    # Row 0: 0.252 * 1000 / 252 = 1.0; Row 1: 0.252 * 2000 / 252 = 2.0
    assert abs(cc[0] - 1.0) < 1e-6
    assert abs(cc[1] - 2.0) < 1e-6


def test_bridge_three_tier(simple_cfg):
    """Bridge sums: Gross→Net via trading costs, Net→Eligible via overhead."""
    pm_net = costs.add_costs(
        _pm_daily(short_notional=0, traded_notional=0), simple_cfg, _pms_df(simple_cfg)
    )
    bridge = costs.bridge_components(pm_net)
    assert bridge["Gross PnL"] == 100.0
    # Trading + Non-trading = Gross
    assert abs(bridge["Trading PnL"] + bridge["Non-trading PnL"] - bridge["Gross PnL"]) < 1e-6
    assert bridge["Financing"] < 0
    # Gross + trading costs → Net PnL
    net_from_bridge = (bridge["Gross PnL"] + bridge["Financing"] + bridge["Borrow"]
                       + bridge["Commission"] + bridge["FX"])
    assert abs(net_from_bridge - bridge["Net PnL"]) < 1e-6
    # Net + overhead → Eligible PnL
    eligible_from_bridge = bridge["Net PnL"] + bridge["Center"] + bridge["Capital Charge"]
    assert abs(eligible_from_bridge - bridge["Eligible PnL"]) < 1e-6
