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
    """Minimal tables that satisfy FK constraints (using DB column names)."""
    strategy_pods = pd.DataFrame([{
        "pod_id": "P1", "pod_name": "Pod 1",
        "strategy_type": "Equity", "pod_aum": 1_000_000,
    }])
    portfolio_managers = pd.DataFrame([{
        "pm_id": "PM_A", "pod_id": "P1", "team_id": "T1",
        "pm_name": "Alice", "pm_aum": 1_000_000,
        "payout_ratio": 0.2, "hurdle_rate": 0.0,
        "initial_hwm": 0.0, "skill": 1.0, "loss_carryforward": 0.0,
    }])
    security_master = pd.DataFrame([{
        "ticker": "EQ001", "asset_class": "Equity", "sector": "Tech",
        "strategy_tag": "Equity-Tech", "beta": 1.0, "alpha": 0.01,
        "idiosyncratic_vol": 0.2,
    }])
    dates = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"])
    eod_prices = pd.DataFrame({
        "date":        list(dates),
        "ticker":      ["EQ001"] * 3,
        "close_price": [100.0, 105.0, 103.0],
    })
    eod_positions = pd.DataFrame({
        "date":     list(dates),
        "pm_id":    ["PM_A"] * 3,
        "ticker":   ["EQ001"] * 3,
        "quantity": [10.0, 12.0, 12.0],  # buy 2 on day 2, hold on day 3
    })
    cfg = {"teams": [{"team_id": "T1", "name": "Team 1"}]}
    return {
        "strategy_pods":      strategy_pods,
        "portfolio_managers": portfolio_managers,
        "security_master":    security_master,
        "eod_prices":         eod_prices,
        "eod_positions":      eod_positions,
    }, cfg


@pytest.fixture
def tmp_db(tiny_tables):
    """Write tiny_tables to a temp DB and yield its path."""
    tables, cfg = tiny_tables
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        write_database(tables, cfg, path=db_path)
        yield db_path


def test_roundtrip_strategy_pods(tmp_db, tiny_tables):
    tables, _ = tiny_tables
    result = read_table("strategy_pods", path=tmp_db)
    assert set(result["pod_id"]) == set(tables["strategy_pods"]["pod_id"])


def test_roundtrip_portfolio_managers_row_count(tmp_db, tiny_tables):
    tables, _ = tiny_tables
    result = read_table("portfolio_managers", path=tmp_db)
    assert len(result) == len(tables["portfolio_managers"])


def test_investment_teams_written(tmp_db):
    teams = read_table("investment_teams", path=tmp_db)
    assert len(teams) == 1
    assert teams.iloc[0]["team_id"] == "T1"
    assert teams.iloc[0]["team_name"] == "Team 1"


def test_fk_columns_present(tmp_db):
    pms = read_table("portfolio_managers", path=tmp_db)
    assert "pod_id" in pms.columns
    assert "team_id" in pms.columns


def test_professional_column_names_in_portfolio_managers(tmp_db):
    pms = read_table("portfolio_managers", path=tmp_db)
    assert "pm_name" in pms.columns
    assert "pm_aum" in pms.columns
    assert "initial_hwm" in pms.columns
    assert "loss_carryforward" in pms.columns


def test_professional_column_names_in_security_master(tmp_db):
    sm = read_table("security_master", path=tmp_db)
    assert "idiosyncratic_vol" in sm.columns


def test_professional_column_names_in_eod_prices(tmp_db):
    prices = read_table("eod_prices", path=tmp_db)
    assert "close_price" in prices.columns


def test_professional_column_names_in_eod_positions(tmp_db):
    positions = read_table("eod_positions", path=tmp_db)
    assert "quantity" in positions.columns


def test_view_vw_manager_hierarchy(tmp_db):
    roster = query("SELECT * FROM vw_manager_hierarchy", path=tmp_db)
    assert "pod_name" in roster.columns
    assert "team_name" in roster.columns
    assert roster.iloc[0]["pod_name"] == "Pod 1"
    assert roster.iloc[0]["team_name"] == "Team 1"


def test_view_vw_mtm_positions(tmp_db):
    pv = query("SELECT * FROM vw_mtm_positions", path=tmp_db)
    assert "nmv" in pv.columns
    # quantity=10, close_price=100 on 2025-01-02 → nmv=1000
    row = pv[pv["date"] == pd.Timestamp("2025-01-02")].iloc[0]
    assert abs(row["nmv"] - 1000.0) < 1e-6


def test_trades_derivation():
    dates = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"])
    positions = pd.DataFrame({
        "date":     list(dates),
        "pm_id":    ["PM_A"] * 3,
        "ticker":   ["EQ001"] * 3,
        "quantity": [10.0, 15.0, 15.0],  # buy 5 on day 2, no change day 3
    })
    prices = pd.DataFrame({
        "date":        list(dates),
        "ticker":      ["EQ001"] * 3,
        "close_price": [100.0, 110.0, 108.0],
    })
    trades = _derive_trades(positions, prices)
    # Only one trade: +5 on 2025-01-03 at execution_price=110
    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["side"] == "BUY"
    assert abs(t["quantity_delta"] - 5.0) < 1e-6
    assert abs(t["trade_notional"] - 550.0) < 1e-6  # 5 * 110


def test_trade_blotter_written_to_db(tmp_db):
    trades = read_table("trade_blotter", path=tmp_db)
    # Day-2 position increase from 10 → 12 should produce one BUY trade
    assert len(trades) >= 1
    assert set(trades["side"]).issubset({"BUY", "SELL"})
    assert "execution_price" in trades.columns
    assert "trade_notional" in trades.columns


def test_list_tables(tmp_db):
    items = list_tables(path=tmp_db)
    names = [n for n, _ in items]
    for expected in ["strategy_pods", "investment_teams", "portfolio_managers",
                     "security_master", "eod_prices", "eod_positions", "trade_blotter"]:
        assert expected in names
    for expected in ["vw_manager_hierarchy", "vw_mtm_positions"]:
        assert expected in names


def test_table_schema_returns_columns(tmp_db):
    cols = table_schema("portfolio_managers", path=tmp_db)
    col_names = [r[1] for r in cols]
    assert "pm_id" in col_names
    assert "pm_aum" in col_names
    assert "payout_ratio" in col_names


def test_idempotent_write(tiny_tables):
    """Calling write_database twice produces the same row count (no duplicates)."""
    tables, cfg = tiny_tables
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        write_database(tables, cfg, path=db_path)
        count1 = len(read_table("eod_positions", path=db_path))
        write_database(tables, cfg, path=db_path)
        count2 = len(read_table("eod_positions", path=db_path))
        assert count1 == count2
