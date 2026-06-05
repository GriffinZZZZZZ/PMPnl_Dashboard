"""Mark-to-market PnL engine.

Daily PnL is **pure mark-to-market** (no realized/unrealized split, no cost-basis
tracking)::

    gross_pnl_t = sum_ticker  qty_{t-1} * (price_t - price_{t-1})

This module builds the enriched per-position daily frame that the cost engine
also consumes (exposure, short notional, traded notional), then rolls PnL up the
hierarchy Position -> PM -> Pod -> Fund and produces cumulative equity curves.
"""
from __future__ import annotations

import pandas as pd


def build_position_frame(prices: pd.DataFrame, positions: pd.DataFrame) -> pd.DataFrame:
    """Join prices onto positions and derive the per-position daily quantities.

    Args:
        prices: long frame with columns ``[date, ticker, price]``.
        positions: long frame with columns ``[date, pm_id, ticker, qty]``.

    Returns:
        A frame indexed by row with columns::

            date, pm_id, ticker, qty, prev_qty, price, prev_price,
            gross_pnl, gross_exposure, short_notional, traded_notional

        The first date per (pm_id, ticker) has zero PnL/costs because there is
        no prior day to mark against.
    """
    df = positions.merge(prices, on=["date", "ticker"], how="left")
    df = df.sort_values(["pm_id", "ticker", "date"]).reset_index(drop=True)

    grp = df.groupby(["pm_id", "ticker"], sort=False)
    df["prev_qty"] = grp["qty"].shift(1)
    df["prev_price"] = grp["price"].shift(1)

    # First observation per series has no prior mark -> treat as flat/no trade.
    df["prev_qty"] = df["prev_qty"].fillna(df["qty"])
    df["prev_price"] = df["prev_price"].fillna(df["price"])

    df["gross_pnl"] = df["prev_qty"] * (df["price"] - df["prev_price"])
    df["gross_exposure"] = (df["prev_qty"] * df["prev_price"]).abs()
    df["short_notional"] = (-df["prev_qty"]).clip(lower=0) * df["prev_price"]
    df["traded_notional"] = (df["qty"] - df["prev_qty"]).abs() * df["price"]
    return df


def pm_daily_gross(position_frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the position frame to daily gross PnL & exposures per PM.

    Returns columns ``[date, pm_id, gross_pnl, gross_exposure, short_notional,
    traded_notional]``.
    """
    agg = (
        position_frame.groupby(["date", "pm_id"], as_index=False)[
            ["gross_pnl", "gross_exposure", "short_notional", "traded_notional"]
        ]
        .sum()
        .sort_values(["pm_id", "date"])
        .reset_index(drop=True)
    )
    return agg


def add_cumulative(df: pd.DataFrame, value_col: str, by: str, out_col: str) -> pd.DataFrame:
    """Add a cumulative-sum column ``out_col`` of ``value_col`` within each ``by`` group."""
    df = df.sort_values([by, "date"]).copy()
    df[out_col] = df.groupby(by, sort=False)[value_col].cumsum()
    return df


def rollup(df: pd.DataFrame, keys: list[str], value_cols: list[str]) -> pd.DataFrame:
    """Generic additive roll-up: sum ``value_cols`` grouped by ``keys``."""
    return df.groupby(keys, as_index=False)[value_cols].sum()
