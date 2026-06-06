"""Synthetic-data generator for the PM PnL dashboard.

Produces deterministic (fixed-seed) but realistic data written to
``data/pm_pnl.db`` (SQLite) with the following tables:

* ``pods``        — one row per pod (strategy bucket).
* ``teams``       — one row per team (from config).
* ``pms``         — one row per PM, with payout terms and skill.
* ``instruments`` — one row per tradable instrument (beta, alpha, idio vol).
* ``prices``      — long format daily prices via a factor model.
* ``positions``   — long format daily quantities (date, pm_id, ticker, qty).
* ``income``      — sparse non-trading income events (other non-recurring income).
* ``trades``      — OMS-style transaction log derived from position changes.

Design rules:
  1. Bottom-up MTM only — PnL is never fabricated; it comes solely from
     quantity x price change, so Position -> PM -> Pod -> Fund reconciles by
     construction.
  2. Factor-structured prices — ``r_{i,t} = beta_i * f_t + eps_{i,t}`` with a
     shared market factor ``f_t``; the co-movement makes netting risk non-trivial.
  3. Per-PM ``skill`` deterministically tilts target weights toward realized
     forward returns (with plenty of noise), so a few PMs end clearly profitable,
     some flat, and one or two underwater.

Run with ``python -m src.data_gen.generate``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import DATA_DIR, load_config
from src.db import write_database

# Trading days per year; dt scales annualized params to daily.
TRADING_DAYS = 252
DT = 1.0 / TRADING_DAYS


def _business_dates(n_days: int, end: str = "2025-12-31") -> pd.DatetimeIndex:
    """Return ``n_days`` business days anchored to ``end`` (deterministic)."""
    return pd.bdate_range(end=end, periods=n_days)


def generate_instruments(cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    """Build the instrument universe with per-instrument beta, alpha, idio vol."""
    asset_classes = cfg["asset_classes"]
    n = cfg["n_instruments"]
    names = list(asset_classes.keys())
    weights = np.array([asset_classes[a]["weight"] for a in names], dtype=float)
    weights = weights / weights.sum()
    counts = np.maximum(1, np.round(weights * n).astype(int))
    while counts.sum() > n:
        counts[np.argmax(counts)] -= 1
    while counts.sum() < n:
        counts[np.argmin(counts)] += 1

    sectors = {
        "Equity": ["Tech", "Financials", "Healthcare", "Industrials", "Consumer"],
        "Rates": ["Govt", "Swaps"],
        "Credit": ["IG", "HY", "Loans"],
        "Commodity": ["Energy", "Metals", "Ags"],
        "FX": ["G10", "EM"],
    }
    rows = []
    idx = 0
    for asset_class, k in zip(names, counts):
        ac = asset_classes[asset_class]
        for _ in range(int(k)):
            idx += 1
            sector = rng.choice(sectors.get(asset_class, [asset_class]))
            rows.append(
                {
                    "ticker": f"{asset_class[:3].upper()}{idx:03d}",
                    "asset_class": asset_class,
                    "sector": str(sector),
                    "strategy_tag": f"{asset_class}-{sector}",
                    "beta": float(ac["beta"] * rng.uniform(0.7, 1.3)),
                    "alpha": float(rng.normal(0.0, ac["alpha_dispersion"])),
                    "idio_vol": float(ac["idio_vol"] * rng.uniform(0.8, 1.2)),
                }
            )
    return pd.DataFrame(rows)


def generate_prices(
    cfg: dict, instruments: pd.DataFrame, dates: pd.DatetimeIndex, rng: np.random.Generator
) -> pd.DataFrame:
    """Simulate daily prices via the factor model and cumulate as GBM.

    ``r_{i,t} = beta_i * f_t + eps_{i,t}``; price = s0 * exp(cumsum(r)).
    """
    n_days = len(dates)
    mkt = cfg["market"]
    # Shared market factor (daily log return).
    f = rng.normal(mkt["mu"] * DT, mkt["sigma"] * np.sqrt(DT), n_days)

    frames = []
    for _, inst in instruments.iterrows():
        eps = rng.normal(inst["alpha"] * DT, inst["idio_vol"] * np.sqrt(DT), n_days)
        log_ret = inst["beta"] * f + eps
        s0 = float(rng.uniform(20, 400))
        path = s0 * np.exp(np.cumsum(log_ret))
        frames.append(pd.DataFrame({"date": dates, "ticker": inst["ticker"], "price": path}))
    return pd.concat(frames, ignore_index=True)


def _zscore(x: np.ndarray) -> np.ndarray:
    """Standardize, guarding against zero variance."""
    sd = x.std()
    return (x - x.mean()) / sd if sd > 0 else np.zeros_like(x)


def generate_positions(
    cfg: dict,
    pms: pd.DataFrame,
    instruments: pd.DataFrame,
    prices: pd.DataFrame,
    dates: pd.DatetimeIndex,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Generate daily long/short positions per PM, tilted toward forward returns.

    Each PM trades a random subset of instruments. Target weights combine a
    skill-scaled signal (z-scored realized forward return) with noise, so higher
    ``skill`` -> positions sit on the right side of moves -> more PnL. Quantities
    then drift day to day (turnover) so commission is non-trivial.
    """
    pm_cfg = cfg["position_model"]
    lev_min, lev_max = pm_cfg["gross_leverage_min"], pm_cfg["gross_leverage_max"]
    noise_scale = pm_cfg["noise_scale"]

    wide = prices.pivot(index="date", columns="ticker", values="price").sort_index()
    p0 = wide.iloc[0]
    # Realized forward return over the whole window per instrument (the "signal").
    fwd_return = (wide.iloc[-1] / wide.iloc[0] - 1.0)

    frames = []
    for _, pm in pms.iterrows():
        cap = pm["allocated_capital"]
        skill = pm["skill"]
        n_names = int(rng.integers(8, 16))
        book = instruments.sample(
            n=min(n_names, len(instruments)), random_state=int(rng.integers(1e9))
        )
        tickers = book["ticker"].to_numpy()

        signal = _zscore(fwd_return.reindex(tickers).to_numpy())
        noise = rng.normal(0.0, noise_scale, len(tickers))
        raw = skill * signal + noise  # signed conviction per name

        abs_raw = np.abs(raw)
        if abs_raw.sum() == 0:
            abs_raw = np.ones_like(abs_raw)
        weight = abs_raw / abs_raw.sum()
        sign = np.where(raw >= 0, 1.0, -1.0)

        gross_leverage = float(rng.uniform(lev_min, lev_max))
        target_gross = cap * gross_leverage

        for tkr, w, s in zip(tickers, weight, sign):
            base_notional = target_gross * w * s
            base_qty = base_notional / float(p0[tkr])
            # Mean-reverting random walk on quantity for turnover.
            qty = np.empty(len(dates))
            q = base_qty
            for i in range(len(dates)):
                q = q + 0.02 * (base_qty - q) + base_qty * 0.03 * rng.standard_normal()
                qty[i] = q
            frames.append(
                pd.DataFrame(
                    {"date": dates, "pm_id": pm["pm_id"], "ticker": tkr, "qty": np.round(qty, 2)}
                )
            )
    return pd.concat(frames, ignore_index=True)


def generate_income(
    cfg: dict,
    pms: pd.DataFrame,
    dates: pd.DatetimeIndex,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Generate sparse per-PM non-trading income events (other non-recurring income).

    These are one-off items — tax reclaims, fee rebates, legal settlements, corporate
    actions, interest true-ups — that are NOT mark-to-market trading PnL. Each PM gets
    ``~annual_events_per_pm`` events (Poisson) on random business days; amounts are
    lognormal around ``amount_mean`` and flipped negative with ``negative_prob``.

    Returns a long frame ``[date, pm_id, category, amount]`` (most days have no row).
    """
    inc = cfg.get("non_trading_income")
    if not inc:
        return pd.DataFrame(columns=["date", "pm_id", "category", "amount"])

    period_fraction = len(dates) / TRADING_DAYS
    lam = inc["annual_events_per_pm"] * period_fraction
    mu = float(np.log(inc["amount_mean"]))
    sigma = float(inc["amount_sigma"])
    neg_p = float(inc["negative_prob"])
    categories = list(inc["categories"])

    rows = []
    for pm_id in pms["pm_id"]:
        n_events = int(rng.poisson(lam))
        if n_events == 0:
            continue
        n_events = min(n_events, len(dates))
        event_days = rng.choice(len(dates), size=n_events, replace=False)
        for di in event_days:
            magnitude = float(np.exp(rng.normal(mu, sigma)))
            sign = -1.0 if rng.random() < neg_p else 1.0
            rows.append({
                "date":     dates[int(di)],
                "pm_id":    pm_id,
                "category": str(rng.choice(categories)),
                "amount":   round(sign * magnitude, 2),
            })
    cols = ["date", "pm_id", "category", "amount"]
    return pd.DataFrame(rows, columns=cols).sort_values(["pm_id", "date"]).reset_index(drop=True)


def generate_all(cfg: dict | None = None) -> dict[str, pd.DataFrame]:
    """Generate every table and write parquet files to ``data/``.

    Returns the dict of DataFrames (also useful for tests / notebooks).
    """
    cfg = cfg or load_config()
    rng = np.random.default_rng(cfg["seed"])
    dates = _business_dates(cfg["n_business_days"], cfg.get("calendar_end", "2025-12-31"))

    pods = pd.DataFrame(cfg["pods"])
    pms = pd.DataFrame(cfg["pms"])
    instruments = generate_instruments(cfg, rng)
    prices = generate_prices(cfg, instruments, dates, rng)
    positions = generate_positions(cfg, pms, instruments, prices, dates, rng)
    income = generate_income(cfg, pms, dates, rng)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Rename columns to match DB schema (generation functions use short internal names).
    pods_db = pods.rename(columns={"name": "pod_name", "allocated_capital": "pod_aum"})

    pms_db = pd.DataFrame(cfg["pms"]).copy()
    pms_db["loss_carryforward"] = (-pms_db["prior_year_pnl"]).clip(lower=0)
    pms_db = pms_db.rename(columns={
        "name": "pm_name", "allocated_capital": "pm_aum", "initial_HWM": "initial_hwm",
    }).drop(columns=["prior_year_pnl"])

    instruments_db = instruments.rename(columns={"idio_vol": "idiosyncratic_vol"})
    prices_db      = prices.rename(columns={"price": "close_price"})
    positions_db   = positions.rename(columns={"qty": "quantity"})

    tables = {
        "strategy_pods":      pods_db,
        "portfolio_managers": pms_db,
        "security_master":    instruments_db,
        "eod_prices":         prices_db,
        "eod_positions":      positions_db,
        "eod_income":         income,
    }
    write_database(tables, cfg)
    return tables


def main() -> None:
    """CLI entry point: generate and print a short summary."""
    tables = generate_all()
    print("Generated synthetic data in", DATA_DIR)
    for name, df in tables.items():
        print(f"  {name:12s}: {len(df):>8,d} rows  cols={list(df.columns)}")


if __name__ == "__main__":
    main()
