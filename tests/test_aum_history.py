"""Tests for generate_aum_history: schema, floor, reallocation properties."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data_gen.generate import (
    _business_dates,
    generate_aum_history,
    generate_instruments,
    generate_positions,
    generate_prices,
)
from src.config import load_config


@pytest.fixture
def _tiny_aum_inputs():
    cfg = load_config()
    rng = np.random.default_rng(42)
    dates = _business_dates(63)   # one quarter
    pms_df = pd.DataFrame(cfg["pms"])
    instruments = generate_instruments(cfg, rng)
    prices = generate_prices(cfg, instruments, dates, rng)
    positions = generate_positions(cfg, pms_df, instruments, prices, dates, rng)
    return cfg, pms_df, prices, positions, dates, rng


def test_schema(_tiny_aum_inputs):
    cfg, pms, prices, positions, dates, rng = _tiny_aum_inputs
    hist = generate_aum_history(cfg, pms, prices, positions, dates, rng)
    assert set(hist.columns) == {"date", "pm_id", "pm_aum"}
    assert hist["pm_aum"].isna().sum() == 0


def test_monthly_frequency(_tiny_aum_inputs):
    """Each PM should have ≥ 2 snapshots (initial + at least one month-end)."""
    cfg, pms, prices, positions, dates, rng = _tiny_aum_inputs
    hist = generate_aum_history(cfg, pms, prices, positions, dates, rng)
    counts = hist.groupby("pm_id").size()
    assert (counts >= 2).all(), "Each PM must have at least an initial + 1 month-end snapshot"


def test_floor_respected(_tiny_aum_inputs):
    """No PM AUM should fall below 20 % of its initial value."""
    cfg, pms, prices, positions, dates, rng = _tiny_aum_inputs
    hist = generate_aum_history(cfg, pms, prices, positions, dates, rng)
    initial = {row["pm_id"]: row["allocated_capital"] for _, row in pms.iterrows()}
    for pm_id, group in hist.groupby("pm_id"):
        floor = initial[pm_id] * 0.20
        assert (group["pm_aum"] >= floor - 1e-3).all(), f"{pm_id} breached floor"


def test_fund_aum_changes(_tiny_aum_inputs):
    """Fund-level AUM (sum of PM AUMs) should vary across snapshots."""
    cfg, pms, prices, positions, dates, rng = _tiny_aum_inputs
    hist = generate_aum_history(cfg, pms, prices, positions, dates, rng)
    fund_by_date = hist.groupby("date")["pm_aum"].sum()
    assert fund_by_date.nunique() > 1, "Fund AUM must change across months"


def test_all_pms_in_every_snapshot(_tiny_aum_inputs):
    """Every snapshot date must contain a row for every PM."""
    cfg, pms, prices, positions, dates, rng = _tiny_aum_inputs
    hist = generate_aum_history(cfg, pms, prices, positions, dates, rng)
    n_pms = len(pms)
    per_date = hist.groupby("date").size()
    assert (per_date == n_pms).all()
