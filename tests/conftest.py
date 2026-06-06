"""Shared fixtures: tiny hand-built frames with known expected results."""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def simple_cfg() -> dict:
    """A minimal config with two equal-capital PMs in two pods.

    Annual cost rates are chosen so that ``rate * exposure * dt`` (dt = 1/252)
    yields clean hand-checkable numbers.

    NOTE: cfg dict keys use the original YAML names (allocated_capital, initial_HWM,
    prior_year_pnl) because engine functions that read cfg directly (attribution
    netting cost, economics AUM) match the YAML schema. Tests that need a
    *DataFrame* of PMs should call pms_df(simple_cfg) to get the DB-column names.
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
        "teams": [
            {"team_id": "T1", "name": "Team 1"},
            {"team_id": "T2", "name": "Team 2"},
        ],
        "pms": [
            {"pm_id": "PM_A", "pod_id": "POD_A", "team_id": "T1", "name": "A1",
             "allocated_capital": 1000, "payout_ratio": 0.2, "hurdle_rate": 0.0,
             "initial_HWM": 0, "skill": 1.0, "prior_year_pnl": 0},
            {"pm_id": "PM_B", "pod_id": "POD_B", "team_id": "T2", "name": "B1",
             "allocated_capital": 1000, "payout_ratio": 0.2, "hurdle_rate": 0.0,
             "initial_HWM": 0, "skill": 1.0, "prior_year_pnl": 0},
        ],
    }


def pms_df(cfg: dict) -> pd.DataFrame:
    """Build a pms DataFrame with DB column names from a cfg dict.

    Use this whenever a test needs a pms DataFrame to pass into an engine
    function (costs.add_costs, payoff.compute_payoff, attribution.*).
    """
    df = pd.DataFrame(cfg["pms"]).copy()
    df["loss_carryforward"] = (-df["prior_year_pnl"]).clip(lower=0)
    return df.rename(columns={
        "name": "pm_name",
        "allocated_capital": "pm_aum",
        "initial_HWM": "initial_hwm",
    }).drop(columns=["prior_year_pnl"])


@pytest.fixture
def two_day_positions() -> tuple[pd.DataFrame, pd.DataFrame]:
    """One PM, one long ticker, two days: close_price 100 -> 110, quantity held at 10."""
    dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
    prices = pd.DataFrame(
        {"date": list(dates), "ticker": ["AAA", "AAA"], "close_price": [100.0, 110.0]}
    )
    positions = pd.DataFrame(
        {"date": list(dates), "pm_id": ["PM_A", "PM_A"], "ticker": ["AAA", "AAA"],
         "quantity": [10.0, 10.0]}
    )
    return prices, positions
