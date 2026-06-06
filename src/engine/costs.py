"""Gross -> Net bridge: daily trading costs + center cost pass-through.

Rates in config are ANNUAL; charged daily via ``dt = 1/252``.
Center cost is a fund overhead allocated to each PM pro-rata by AUM share and
charged daily — a pass-through so comp is paid on net after center cost::

    financing_{pm,t}  = financing_rate * gross_exposure_{pm,t-1} * dt
    borrow_{pm,t}     = borrow_rate    * short_notional_{pm,t-1} * dt
    commission_{pm,t} = (commission_bps / 1e4) * traded_notional_{pm,t}
    fx_{pm,t}         = fx_rate        * fx_notional_{pm,t-1}     * dt
    center_{pm,t}     = center_cost_annual * (pm_capital / fund_capital) * dt
    pm_net_t          = pm_gross_t - financing - borrow - commission - fx - center

With center as a pass-through, the investor waterfall becomes:
    investor_net = fund_net_pnl - total_comp    (no second center deduction)
"""
from __future__ import annotations

import pandas as pd

TRADING_DAYS = 252
DT = 1.0 / TRADING_DAYS


def _center_daily(cfg: dict, pm_capital: float, fund_capital: float) -> float:
    """Daily center cost for one PM (constant)."""
    annual = cfg["center_cost"]["bps_on_aum"] / 1e4 * sum(
        p["allocated_capital"] for p in cfg["pods"]
    )
    return annual * (pm_capital / fund_capital) * DT


def add_costs(pm_daily: pd.DataFrame, cfg: dict, pms: pd.DataFrame) -> pd.DataFrame:
    """Append daily cost columns and ``net_pnl`` to a per-PM daily frame.

    Args:
        pm_daily: output of :func:`src.engine.pnl.pm_daily_gross` with columns
            ``[date, pm_id, gross_pnl, gross_exposure, short_notional,
              traded_notional, fx_notional]``.
        cfg: parsed config; reads ``cfg['costs']`` and ``cfg['center_cost']``.
        pms: PM roster with ``[pm_id, allocated_capital]``.

    Returns:
        Frame with added columns
        ``[financing, borrow, commission, fx, center, total_cost, net_pnl]``.
    """
    c = cfg["costs"]
    fund_cap = float(sum(p["allocated_capital"] for p in cfg["pods"]))
    cap_map = pms.set_index("pm_id")["allocated_capital"].to_dict()

    df = pm_daily.copy()
    df["financing"] = c["financing_rate"] * df["gross_exposure"] * DT
    df["borrow"] = c["borrow_rate"] * df["short_notional"] * DT
    df["commission"] = (c["commission_bps"] / 1e4) * df["traded_notional"]
    df["fx"] = c.get("fx_rate", 0.0) * df.get("fx_notional", 0.0) * DT
    df["center"] = df["pm_id"].map(
        {pm: _center_daily(cfg, cap, fund_cap) for pm, cap in cap_map.items()}
    )
    df["total_cost"] = df["financing"] + df["borrow"] + df["commission"] + df["fx"] + df["center"]
    df["net_pnl"] = df["gross_pnl"] - df["total_cost"]
    return df


def bridge_components(pm_net_daily: pd.DataFrame, pm_ids: list[str] | None = None) -> dict:
    """Summed Gross -> PM Net bridge components (deductions are negative).

    Components: Financing, Borrow, Commission, FX, Center → PM Net.
    """
    df = pm_net_daily if pm_ids is None else pm_net_daily[pm_net_daily["pm_id"].isin(pm_ids)]
    return {
        "Gross PnL": float(df["gross_pnl"].sum()),
        "Financing": -float(df["financing"].sum()),
        "Borrow": -float(df["borrow"].sum()),
        "Commission": -float(df["commission"].sum()),
        "FX": -float(df.get("fx", 0).sum() if "fx" in df.columns else 0),
        "Center": -float(df["center"].sum()),
        "PM Net": float(df["net_pnl"].sum()),
    }
