"""Round-trip tests for the SQLite data-access layer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.db import (
    _derive_trades,
    connect,
    list_tables,
    query,
    read_table,
    table_schema,
    write_database,
)


@pytest.fixture
def tiny_tables():
    """Minimal tables that satisfy FK constraints."""
    pods = pd.DataFrame([
        {"pod_id": "P1", "name": "Pod 1", "strategy_type": "Equity", "allocated_capital": 1_000_000}
    ])
    teams = pd.DataFrame([{"team_id": "T1", "name": "Team 1"}])
    pms = pd.DataFrame([
        {"pm_id": "PM_A", "pod_id": "P1", "team_id": "T1", "name": "Alice",
         "allocated_capital": 1_000_000, "payout_ratio": 0.2, "hurdle_rate": 0.0,
         "initial_HWM": 0.0, "skill": 1.0, "prior_year_pnl": 0.0}
    ])
    instruments = pd.DataFrame([
        {"ticker": "EQ001", "asset_class": "Equity", "sector": "Tech",
         "strategy_tag": "Equity-Tech", "beta": 1.0, "alpha": 0.01, "idio_vol": 0.2}
    ])
    dates = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"])
    prices = pd.DataFrame({
        "date":   list(dates) * 1,
        "ticker": ["EQ001"] * 3,
        "price":  [100.0, 105.0, 103.0],
    })
    positions = pd.DataFrame({
        "date":   list(dates),
        "pm_id":  ["PM_A"] * 3,
        "ticker": ["EQ001"] * 3,
        "qty":    [10.0, 12.0, 12.0],  # buy 2 on day 2, hold on day 3
    })
    cfg = {"teams": [{"team_id": "T1", "name": "Team 1"}]}
    return {"pods": pods, "pms": pms, "instruments": instruments,
            "prices": prices, "positions": positions}, cfg


@pytest.fixture
def tmp_db(tiny_tables):
    """Write tiny_tables to a temp DB and yield its path."""
    tables, cfg = tiny_tables
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        write_database(tables, cfg, path=db_path)
        yield db_path


def test_roundtrip_pods(tmp_db, tiny_tables):
    tables, _ = tiny_tables
    result = read_table("pods", path=tmp_db)
    assert set(result["pod_id"]) == set(tables["pods"]["pod_id"])


def test_roundtrip_pms_row_count(tmp_db, tiny_tables):
    tables, _ = tiny_tables
    result = read_table("pms", path=tmp_db)
    assert len(result) == len(tables["pms"])


def test_teams_table_written(tmp_db):
    teams = read_table("teams", path=tmp_db)
    assert len(teams) == 1
    assert teams.iloc[0]["team_id"] == "T1"


def test_fk_columns_present(tmp_db):
    pms = read_table("pms", path=tmp_db)
    assert "pod_id" in pms.columns
    assert "team_id" in pms.columns


def test_view_v_pm_roster(tmp_db):
    roster = query("SELECT * FROM v_pm_roster", path=tmp_db)
    assert "pod_name" in roster.columns
    assert "team_name" in roster.columns
    assert roster.iloc[0]["pod_name"] == "Pod 1"
    assert roster.iloc[0]["team_name"] == "Team 1"


def test_view_v_position_value(tmp_db):
    pv = query("SELECT * FROM v_position_value", path=tmp_db)
    assert "nmv" in pv.columns
    # qty=10, price=100 on 2025-01-02 → nmv=1000
    row = pv[pv["date"] == pd.Timestamp("2025-01-02")].iloc[0]
    assert abs(row["nmv"] - 1000.0) < 1e-6


def test_trades_derivation():
    dates = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"])
    positions = pd.DataFrame({
        "date":   list(dates),
        "pm_id":  ["PM_A"] * 3,
        "ticker": ["EQ001"] * 3,
        "qty":    [10.0, 15.0, 15.0],  # buy 5 on day 2, no change day 3
    })
    prices = pd.DataFrame({
        "date":   list(dates),
        "ticker": ["EQ001"] * 3,
        "price":  [100.0, 110.0, 108.0],
    })
    trades = _derive_trades(positions, prices)
    # Only one trade: +5 on 2025-01-03
    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["side"] == "BUY"
    assert abs(t["qty_change"] - 5.0) < 1e-6
    assert abs(t["notional"] - 550.0) < 1e-6  # 5 * 110


def test_trades_written_to_db(tmp_db):
    trades = read_table("trades", path=tmp_db)
    # Day-2 position increase from 10 → 12 should produce one BUY trade
    assert len(trades) >= 1
    assert set(trades["side"]).issubset({"BUY", "SELL"})


def test_list_tables(tmp_db):
    items = list_tables(path=tmp_db)
    names = [n for n, _ in items]
    for expected in ["pods", "teams", "pms", "instruments", "prices", "positions", "trades"]:
        assert expected in names
    for expected in ["v_pm_roster", "v_position_value"]:
        assert expected in names


def test_table_schema_returns_columns(tmp_db):
    cols = table_schema("pms", path=tmp_db)
    col_names = [r[1] for r in cols]
    assert "pm_id" in col_names
    assert "payout_ratio" in col_names


def test_idempotent_write(tiny_tables):
    """Calling write_database twice produces the same row count (no duplicates)."""
    tables, cfg = tiny_tables
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        write_database(tables, cfg, path=db_path)
        count1 = len(read_table("positions", path=db_path))
        write_database(tables, cfg, path=db_path)
        count2 = len(read_table("positions", path=db_path))
        assert count1 == count2
