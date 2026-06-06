"""Data loading + end-to-end computation, shared by every dashboard page.

``compute_all`` runs the full engine once and returns a single results bundle so
the four pages all read consistent numbers. Results are cached with
``st.cache_data`` when Streamlit is running; outside Streamlit (``run.py``,
pytest) the decorator degrades to a plain pass-through.
"""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from src.config import DATA_DIR, load_config
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


TABLES = ["pods", "pms", "instruments", "prices", "positions"]


@_cache(show_spinner=False)
def load_all() -> dict[str, pd.DataFrame]:
    """Load every parquet table from ``data/`` into a dict of DataFrames."""
    missing = [t for t in TABLES if not (DATA_DIR / f"{t}.parquet").exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing data tables {missing}. Run `python -m src.data_gen.generate` first."
        )
    return {t: pd.read_parquet(DATA_DIR / f"{t}.parquet") for t in TABLES}


@_cache(show_spinner=False)
def compute_all(payout_ratio_override: float | None = None) -> dict[str, Any]:
    """Run the full engine and return the results bundle used by all pages.

    Args:
        payout_ratio_override: optional fund-wide payout ratio for the dashboard
            sensitivity slider. ``None`` uses each PM's configured ratio.

    Returns:
        A dict with raw rosters, daily frames, roll-ups, and fund economics.
    """
    cfg = load_config()
    raw = load_all()
    pods, pms, instruments = raw["pods"], raw["pms"], raw["instruments"]

    position_frame = pnl.build_position_frame(raw["prices"], raw["positions"], instruments)
    pm_daily = pnl.pm_daily_gross(position_frame)
    pm_net_daily = costs.add_costs(pm_daily, cfg, pms)

    payoff_daily = payoff.compute_payoff(pm_net_daily, pms, cfg, payout_ratio_override)
    total_comp = float(payoff.total_comp_by_pm(payoff_daily)["total_comp"].sum())

    fund_net = float(pm_net_daily["net_pnl"].sum())
    fund_gross = float(pm_net_daily["gross_pnl"].sum())
    econ = economics.investor_economics(fund_net, total_comp, cfg)

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
        "fund_gross": fund_gross,
        "fund_net": fund_net,
        "total_comp": total_comp,
        "center_cost": econ["center_cost"],
        "investor_net": econ["investor_net"],
        "comp_expense_ratio": econ["comp_expense_ratio"],
        "aum": econ["aum"],
        "netting_cost": attribution.netting_cost(total_comp, fund_net, cfg),
        "hypothetical_netted_comp": attribution.hypothetical_netted_comp(fund_net, cfg),
        "prices": raw["prices"],
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
