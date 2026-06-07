"""Non-trading income generation (eod_income): determinism, schema, reconciliation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data_gen.generate import generate_income

_DATES = pd.bdate_range(end="2025-12-31", periods=252)


def _pms() -> pd.DataFrame:
    return pd.DataFrame({"pm_id": ["PM_A", "PM_B", "PM_C"]})


def _cfg() -> dict:
    return {
        "non_trading_income": {
            "annual_events_per_pm": 6,
            "amount_mean": 150000,
            "amount_sigma": 0.8,
            "negative_prob": 0.15,
            "categories": ["Tax Reclaim", "Fee Rebate", "Legal Settlement",
                           "Corporate Action", "Interest True-up"],
        }
    }


def test_generate_income_is_deterministic():
    """Same seed → byte-identical events."""
    a = generate_income(_cfg(), _pms(), _DATES, np.random.default_rng(42))
    b = generate_income(_cfg(), _pms(), _DATES, np.random.default_rng(42))
    pd.testing.assert_frame_equal(a, b)


def test_generate_income_schema_and_domain():
    """Columns, category domain, and finite amounts."""
    df = generate_income(_cfg(), _pms(), _DATES, np.random.default_rng(7))
    assert list(df.columns) == ["date", "pm_id", "category", "amount"]
    assert set(df["category"]).issubset(set(_cfg()["non_trading_income"]["categories"]))
    assert set(df["pm_id"]).issubset({"PM_A", "PM_B", "PM_C"})
    assert np.isfinite(df["amount"]).all()
    assert df["date"].isin(_DATES).all()


def test_some_events_can_be_negative():
    """With negative_prob > 0 over many events, at least one charge appears."""
    df = generate_income(_cfg(), _pms(), _DATES, np.random.default_rng(1))
    assert (df["amount"] < 0).any()


def test_no_config_returns_empty_frame():
    """A config without a non_trading_income block yields an empty, well-formed frame."""
    df = generate_income({}, _pms(), _DATES, np.random.default_rng(0))
    assert list(df.columns) == ["date", "pm_id", "category", "amount"]
    assert df.empty
