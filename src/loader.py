"""Data loading + end-to-end computation, shared by every dashboard page.

``compute_all`` runs the full engine once and returns a single results bundle so
the four pages all read consistent numbers. Results are cached with
``st.cache_data`` when Streamlit is running; outside Streamlit (``run.py``,
pytest) the decorator degrades to a plain pass-through.
"""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from src.config import DB_PATH, load_config
from src.db import read_table
from src.engine import attribution, costs, economics, payoff, pnl

# --- cache decorator that works with or without a Streamlit runtime -----------
def _passthrough(func=None, **_kwargs):  # type: ignore
    """No-op stand-in for ``st.cache_data`` outside a Streamlit runtime."""

    def wrap(f):
        return f

    return wrap(func) if callable(func) else wrap


try:  # pragma: no cover - exercised implicitly
    import streamlit as st

    # Only use the real cache when an actual Streamlit runtime exists; otherwise
    # (run.py, pytest) fall back to a plain pass-through to avoid noisy warnings.
    if st.runtime.exists():
        _cache: Callable = st.cache_data
    else:
        _cache = _passthrough
except Exception:  # streamlit not installed
    _cache = _passthrough


_DB_TABLES = ["strategy_pods", "portfolio_managers", "security_master", "eod_prices",
              "eod_positions", "eod_income"]


@_cache(show_spinner=False)
def load_all() -> dict[str, pd.DataFrame]:
    """Load engine tables from ``data/pm_pnl.db`` into a dict of DataFrames."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. Run `python run.py` first."
        )
    return {t: read_table(t) for t in _DB_TABLES}


@_cache(show_spinner=False)
def compute_all(
    payout_ratio_override: float | None = None,
    date_from: str | None = None,
    date_to:   str | None = None,
) -> dict[str, Any]:
    """Run the full engine and return the results bundle used by all pages.

    Args:
        payout_ratio_override: optional fund-wide payout ratio for the sensitivity slider.
        date_from: ISO date string (YYYY-MM-DD) for start of analysis window; defaults to all data.
        date_to:   ISO date string for end of analysis window.

    Returns:
        A dict with raw rosters, daily frames, roll-ups, and fund economics.
    """
    cfg = load_config()
    raw = load_all()
    pods        = raw["strategy_pods"]
    pms         = raw["portfolio_managers"]
    instruments = raw["security_master"]

    # Apply date filter before engine runs (affects PnL, costs, and comp calculations).
    prices_f    = raw["eod_prices"].copy()
    positions_f = raw["eod_positions"].copy()
    income_f    = raw["eod_income"].copy()
    if date_from:
        dt_from = pd.Timestamp(date_from)
        prices_f    = prices_f[prices_f["date"] >= dt_from]
        positions_f = positions_f[positions_f["date"] >= dt_from]
        income_f    = income_f[income_f["date"] >= dt_from]
    if date_to:
        dt_to = pd.Timestamp(date_to)
        prices_f    = prices_f[prices_f["date"] <= dt_to]
        positions_f = positions_f[positions_f["date"] <= dt_to]
        income_f    = income_f[income_f["date"] <= dt_to]

    position_frame = pnl.build_position_frame(prices_f, positions_f, instruments)
    pm_daily = pnl.pm_daily_gross(position_frame)

    # Merge non-trading income (other non-recurring income) onto the PM-daily frame.
    income_daily = (
        income_f.groupby(["date", "pm_id"], as_index=False)["amount"].sum()
        .rename(columns={"amount": "non_trading_pnl"})
    )
    pm_daily = pm_daily.merge(income_daily, on=["date", "pm_id"], how="left")
    pm_daily["non_trading_pnl"] = pm_daily["non_trading_pnl"].fillna(0.0)

    pm_net_daily = costs.add_costs(pm_daily, cfg, pms)

    payoff_daily = payoff.compute_payoff(pm_net_daily, pms, cfg, payout_ratio_override)
    total_comp = float(payoff.total_comp_by_pm(payoff_daily)["total_comp"].sum())

    # Drawdown per PM: how far cum_net sits below the running HWM (negative = below).
    drawdown_by_pm = (
        payoff_daily.assign(drawdown=lambda d: d["cum_net"] - d["hwm"])
        .groupby("pm_id")["drawdown"]
        .min()
        .rename("max_drawdown")
    )

    fund_trading          = float(pm_net_daily["trading_pnl"].sum())
    fund_non_trading      = float(pm_net_daily["non_trading_pnl"].sum())
    fund_gross            = float(pm_net_daily["gross_pnl"].sum())
    fund_net              = float(pm_net_daily["net_pnl"].sum())
    fund_eligible         = float(pm_net_daily["eligible_pnl"].sum())
    fund_capital_charges  = float(pm_net_daily["capital_charge"].sum())
    income_total          = float(income_f["amount"].sum())
    position_trading      = float(position_frame["gross_pnl"].sum())
    fund_base_comp        = economics.base_comp_total(cfg)
    fund_mgmt_fee         = economics.management_fee_total(cfg)
    econ = economics.investor_economics(
        fund_eligible, total_comp, cfg,
        capital_charges=fund_capital_charges,
        base_comp=fund_base_comp,
        mgmt_fee=fund_mgmt_fee,
    )

    return {
        "cfg": cfg,
        "pods": pods,
        "pms": pms,
        "instruments": instruments,
        "position_frame": position_frame,
        "pm_net_daily": pm_net_daily,
        "payoff_daily": payoff_daily,
        "total_comp_by_pm": payoff.total_comp_by_pm(payoff_daily),
        "effective_payout_rates": payoff.effective_payout_rates(payoff_daily),
        "fund_trading":         fund_trading,
        "fund_non_trading":     fund_non_trading,
        "fund_gross":           fund_gross,
        "fund_net":             fund_net,
        "fund_eligible_pnl":    fund_eligible,
        "fund_capital_charges": fund_capital_charges,
        "fund_base_comp":       fund_base_comp,
        "fund_mgmt_fee":        fund_mgmt_fee,
        "income_total":         income_total,
        "position_trading":     position_trading,
        "eod_income":           income_f,
        "total_comp":           total_comp,
        "center_cost":          econ["center_cost"],
        "investor_net":         econ["investor_net"],
        "comp_expense_ratio":   econ["comp_expense_ratio"],
        "aum":                  econ["aum"],
        "drawdown_by_pm":       drawdown_by_pm,
        "netting_cost": attribution.netting_cost(total_comp, fund_net, cfg),
        "hypothetical_netted_comp": attribution.hypothetical_netted_comp(fund_net, cfg),
        "prices": prices_f,
    }


def fund_equity_curve(pm_net_daily: pd.DataFrame) -> pd.DataFrame:
    """Fund-level cumulative gross & net equity curve indexed by date."""
    daily = pm_net_daily.groupby("date", as_index=False)[["gross_pnl", "net_pnl"]].sum()
    daily = daily.sort_values("date")
    daily["Gross"] = daily["gross_pnl"].cumsum()
    daily["Net"] = daily["net_pnl"].cumsum()
    return daily.set_index("date")[["Gross", "Net"]]


def comp_liability_curve(payoff_daily: pd.DataFrame, pm_net_daily: pd.DataFrame) -> pd.DataFrame:
    """Daily accrued comp liability and its share of cumulative **gross** PnL.

    Using cumulative gross as the denominator (instead of net) avoids the >100%
    spike that occurs when losers drag net PnL close to zero while winners keep
    accruing comp. Gross is always positive once the fund is profitable on gross.
    """
    comp = payoff_daily.groupby("date")["accrued_comp"].sum().sort_index()
    cum_gross = pm_net_daily.groupby("date")["gross_pnl"].sum().sort_index().cumsum()
    out = pd.DataFrame({"comp": comp, "cum_gross": cum_gross})
    denom = out["cum_gross"].where(out["cum_gross"] > 0)
    out["comp_pct_of_gross"] = out["comp"] / denom
    return out[["comp", "comp_pct_of_gross"]]


def fund_nav_curve(pm_net_daily: pd.DataFrame, aum_value: float) -> pd.DataFrame:
    """Fund NAV = initial AUM + cumulative net PnL, indexed by date."""
    daily = pm_net_daily.groupby("date")["net_pnl"].sum().sort_index()
    cum_net = daily.cumsum()
    return pd.DataFrame({"NAV": aum_value + cum_net})
