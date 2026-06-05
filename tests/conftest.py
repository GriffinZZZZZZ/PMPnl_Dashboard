"""Shared fixtures: tiny hand-built frames with known expected results."""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def simple_cfg() -> dict:
    """A minimal config with two equal-capital PMs in two pods.

    Annual cost rates are chosen so that ``rate * exposure * dt`` (dt = 1/252)
    yields clean hand-checkable numbers.
    """
    return {
        "n_business_days": 252,
        "costs": {
            "financing_rate": 0.252,   # * dt = 0.001 daily
            "borrow_rate": 0.504,      # * dt = 0.002 daily
            "commission_bps": 10.0,    # 10 bps = 0.001
        },
        "center_cost": {"bps_on_aum": 100.0},  # 1% of AUM
        "pods": [
            {"pod_id": "POD_A", "name": "A", "strategy_type": "x", "allocated_capital": 1000},
            {"pod_id": "POD_B", "name": "B", "strategy_type": "y", "allocated_capital": 1000},
        ],
        "pms": [
            {"pm_id": "PM_A", "pod_id": "POD_A", "name": "A1", "allocated_capital": 1000,
             "payout_ratio": 0.2, "hurdle_rate": 0.0, "initial_HWM": 0, "skill": 1.0},
            {"pm_id": "PM_B", "pod_id": "POD_B", "name": "B1", "allocated_capital": 1000,
             "payout_ratio": 0.2, "hurdle_rate": 0.0, "initial_HWM": 0, "skill": 1.0},
        ],
    }


@pytest.fixture
def two_day_positions() -> tuple[pd.DataFrame, pd.DataFrame]:
    """One PM, one long ticker, two days: price 100 -> 110, qty held at 10."""
    dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
    prices = pd.DataFrame(
        {"date": list(dates), "ticker": ["AAA", "AAA"], "price": [100.0, 110.0]}
    )
    positions = pd.DataFrame(
        {"date": list(dates), "pm_id": ["PM_A", "PM_A"], "ticker": ["AAA", "AAA"],
         "qty": [10.0, 10.0]}
    )
    return prices, positions
