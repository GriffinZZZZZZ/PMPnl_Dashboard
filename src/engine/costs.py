"""Gross → Net → Eligible PnL bridge: three-tier daily cost attribution.

Rates in config are ANNUAL; charged daily via ``dt = 1/252``.

Tier 1 — Trading costs (market-facing, booked against gross PnL):
    financing_{pm,t}  = financing_rate * gross_exposure_{pm,t-1} * dt
    borrow_{pm,t}     = borrow_rate    * short_notional_{pm,t-1} * dt
    commission_{pm,t} = (commission_bps / 1e4) * traded_notional_{pm,t}
    fx_{pm,t}         = fx_rate        * fx_notional_{pm,t-1}     * dt
    net_pnl           = gross_pnl - trading_cost

Tier 2 — Overhead costs (fund structure, booked against net PnL):
    center_{pm,t}         = center_cost_annual * (pm_aum / fund_aum) * dt
    capital_charge_{pm,t} = hurdle_rate * pm_aum * dt  (cost of capital, not a threshold)
    eligible_pnl          = net_pnl - center - capital_charge

Incentive comp accrues on ``eligible_pnl`` against the PM's high-water mark.
Investor net = fund eligible PnL - total comp.
"""
from __future__ import annotations

import pandas as pd

TRADING_DAYS = 252
DT = 1.0 / TRADING_DAYS


def _center_daily(cfg: dict, pm_capital: float, fund_capital: float) -> float:
    """Daily center overhead cost for one PM (constant throughout the period)."""
    annual = cfg["center_cost"]["bps_on_aum"] / 1e4 * sum(
        p["allocated_capital"] for p in cfg["pods"]
    )
    return annual * (pm_capital / fund_capital) * DT


def add_costs(pm_daily: pd.DataFrame, cfg: dict, pms: pd.DataFrame) -> pd.DataFrame:
    """Append cost columns, net_pnl, and eligible_pnl to a per-PM daily frame.

    Args:
        pm_daily: output of :func:`src.engine.pnl.pm_daily_gross`.
        cfg: parsed config; reads ``cfg['costs']`` and ``cfg['center_cost']``.
        pms: PM roster with ``[pm_id, pm_aum, hurdle_rate]``.

    Returns:
        Frame with added columns::

            financing, borrow, commission, fx, center, capital_charge,
            trading_cost, overhead_cost, total_cost,
            net_pnl, eligible_pnl
    """
    c = cfg["costs"]
    fund_cap  = float(sum(p["allocated_capital"] for p in cfg["pods"]))
    cap_map   = pms.set_index("pm_id")["pm_aum"].to_dict()
    hurdle_map = pms.set_index("pm_id")["hurdle_rate"].to_dict()

    df = pm_daily.copy()

    # --- Tier 1: trading costs ---
    df["financing"]  = c["financing_rate"] * df["gross_exposure"] * DT
    df["borrow"]     = c["borrow_rate"]    * df["short_notional"] * DT
    df["commission"] = (c["commission_bps"] / 1e4) * df["traded_notional"]
    df["fx"]         = c.get("fx_rate", 0.0) * df.get("fx_notional", 0.0) * DT
    df["trading_cost"] = df["financing"] + df["borrow"] + df["commission"] + df["fx"]
    df["net_pnl"]      = df["gross_pnl"] - df["trading_cost"]

    # --- Tier 2: overhead costs ---
    df["center"] = df["pm_id"].map(
        {pm: _center_daily(cfg, cap, fund_cap) for pm, cap in cap_map.items()}
    )
    df["capital_charge"] = df["pm_id"].map(
        {pm: hurdle_map[pm] * cap_map[pm] * DT for pm in hurdle_map}
    )
    df["overhead_cost"] = df["center"] + df["capital_charge"]
    df["eligible_pnl"]  = df["net_pnl"] - df["overhead_cost"]

    df["total_cost"] = df["trading_cost"] + df["overhead_cost"]
    return df


def bridge_components(pm_net_daily: pd.DataFrame, pm_ids: list[str] | None = None) -> dict:
    """Three-tier Gross → Net → Eligible bridge (deductions are negative).

    Returns ordered dict: Gross / trading costs / Net / overhead / Eligible.
    """
    df = pm_net_daily if pm_ids is None else pm_net_daily[pm_net_daily["pm_id"].isin(pm_ids)]
    return {
        "Gross PnL":      float(df["gross_pnl"].sum()),
        "Financing":      -float(df["financing"].sum()),
        "Borrow":         -float(df["borrow"].sum()),
        "Commission":     -float(df["commission"].sum()),
        "FX":             -float(df["fx"].sum() if "fx" in df.columns else 0),
        "Net PnL":        float(df["net_pnl"].sum()),
        "Center":         -float(df["center"].sum()),
        "Capital Charge": -float(df["capital_charge"].sum()),
        "Eligible PnL":   float(df["eligible_pnl"].sum()),
    }
