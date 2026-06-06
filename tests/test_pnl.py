"""Mark-to-market PnL: hand-verified."""
from __future__ import annotations

import pandas as pd

from src.engine import pnl


def test_build_position_frame_mtm(two_day_positions):
    prices, positions = two_day_positions
    pf = pnl.build_position_frame(prices, positions)

    day2 = pf[pf["date"] == pd.Timestamp("2024-01-02")].iloc[0]
    # quantity_{t-1}=10, price change = 110-100 = 10  ->  gross_pnl = 100
    assert day2["gross_pnl"] == 100.0
    # gross exposure = |prev_quantity * prev_price| = 10 * 100 = 1000
    assert day2["gross_exposure"] == 1000.0
    # long book -> long_notional = 1000, no short notional (financing charges longs only)
    assert day2["long_notional"] == 1000.0
    assert day2["short_notional"] == 0.0
    assert day2["traded_notional"] == 0.0
    # first day has no prior mark -> zero pnl
    day1 = pf[pf["date"] == pd.Timestamp("2024-01-01")].iloc[0]
    assert day1["gross_pnl"] == 0.0


def test_short_position_metrics():
    dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
    prices = pd.DataFrame({"date": list(dates), "ticker": ["S", "S"], "close_price": [50.0, 40.0]})
    positions = pd.DataFrame(
        {"date": list(dates), "pm_id": ["P", "P"], "ticker": ["S", "S"], "quantity": [-20.0, -20.0]}
    )
    pf = pnl.build_position_frame(prices, positions)
    day2 = pf[pf["date"] == dates[1]].iloc[0]
    # short 20 @ price drop 50->40 = +200 PnL for the short
    assert day2["gross_pnl"] == 200.0
    # short notional = 20 * 50 = 1000; long_notional = 0 (so no financing on this short)
    assert day2["short_notional"] == 1000.0
    assert day2["long_notional"] == 0.0


def test_traded_notional_on_turnover():
    dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
    prices = pd.DataFrame({"date": list(dates), "ticker": ["T", "T"], "close_price": [10.0, 10.0]})
    positions = pd.DataFrame(
        {"date": list(dates), "pm_id": ["P", "P"], "ticker": ["T", "T"], "quantity": [5.0, 8.0]}
    )
    pf = pnl.build_position_frame(prices, positions)
    day2 = pf[pf["date"] == dates[1]].iloc[0]
    # |8 - 5| * close_price(10) = 30
    assert day2["traded_notional"] == 30.0


def test_rollup_is_additive():
    df = pd.DataFrame(
        {"pod_id": ["A", "A", "B"], "net_pnl": [1.0, 2.0, 3.0]}
    )
    out = pnl.rollup(df, ["pod_id"], ["net_pnl"]).set_index("pod_id")["net_pnl"]
    assert out["A"] == 3.0 and out["B"] == 3.0
