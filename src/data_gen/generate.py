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


def _business_dates(n_days: int, start: str = "2025-01-02") -> pd.DatetimeIndex:
    """Return ``n_days`` business days starting from ``start`` (deterministic)."""
    return pd.bdate_range(start=start, periods=n_days)


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


def generate_aum_history(
    cfg: dict,
    pms: pd.DataFrame,
    prices: pd.DataFrame,
    positions: pd.DataFrame,
    dates: pd.DatetimeIndex,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Monthly PM AUM snapshots driven by realized performance ranking.

    Uses already-generated positions + prices to rank PMs by cumulative MTM
    return each month-end, then reallocates capital from underperformers to
    outperformers. Fund-level AUM also drifts via simulated investor flows.

    Returns [date, pm_id, pm_aum] with one row per PM per snapshot date.
    The first snapshot is at dates[0] (initial state); subsequent snapshots
    are at business-month-end dates.
    """
    dyn = cfg.get("aum_dynamics", {})
    mean_bps    = float(dyn.get("monthly_flow_mean_bps", 50))
    std_bps     = float(dyn.get("monthly_flow_std_bps", 150))
    r_lo, r_hi  = dyn.get("reallocation_range", [0.05, 0.12])
    n_realloc   = int(dyn.get("n_reallocated", 3))
    floor_pct   = 0.20  # PM AUM floor = 20 % of initial

    # Rough daily MTM PnL: prev_qty × Δprice (no costs, good enough for ranking).
    merged = (
        positions.sort_values(["pm_id", "ticker", "date"])
        .merge(prices[["date", "ticker", "price"]], on=["date", "ticker"])
    )
    merged["prev_price"] = merged.groupby(["pm_id", "ticker"])["price"].shift(1)
    merged["prev_qty"]   = merged.groupby(["pm_id", "ticker"])["qty"].shift(1)
    merged = merged.dropna(subset=["prev_price", "prev_qty"])
    merged["daily_pnl"] = merged["prev_qty"] * (merged["price"] - merged["prev_price"])
    pnl_by_day = merged.groupby(["date", "pm_id"])["daily_pnl"].sum().reset_index()
    pnl_by_day = pnl_by_day.sort_values(["pm_id", "date"])
    pnl_by_day["cum_pnl"] = pnl_by_day.groupby("pm_id")["daily_pnl"].cumsum()

    # Business-month-end dates within the simulation window.
    monthly_ends = (
        pd.Series(dates)
        .to_frame("date")
        .assign(ym=lambda d: d["date"].dt.to_period("M"))
        .groupby("ym")["date"]
        .last()
        .to_numpy()
    )

    initial_aum = {row["pm_id"]: float(row["allocated_capital"]) for _, row in pms.iterrows()}
    floors      = {pm: v * floor_pct for pm, v in initial_aum.items()}
    current_aum = dict(initial_aum)
    pm_ids      = list(current_aum.keys())

    rows: list[dict] = []
    for pm_id in pm_ids:                              # initial snapshot
        rows.append({"date": dates[0], "pm_id": pm_id, "pm_aum": current_aum[pm_id]})

    for month_end in monthly_ends:
        # Cumulative return per PM up to this month-end.
        snap = (
            pnl_by_day[pnl_by_day["date"] <= month_end]
            .groupby("pm_id")["cum_pnl"].last()
        )
        ret = {pm: float(snap.get(pm, 0.0)) / current_aum[pm] for pm in pm_ids}
        ranked  = sorted(pm_ids, key=lambda pm: ret[pm], reverse=True)
        winners = ranked[:n_realloc]
        losers  = ranked[-n_realloc:]

        # Within-fund reallocation (zero-sum): cut from losers, give to winners.
        cut_amts  = [current_aum[pm] * float(rng.uniform(r_lo, r_hi)) for pm in losers]
        gain_amts = [current_aum[pm] * float(rng.uniform(r_lo, r_hi)) for pm in winners]
        total_cut  = sum(cut_amts)
        total_gain = sum(gain_amts)
        scale = total_cut / total_gain if total_gain > 0 else 0.0

        for pm, amt in zip(losers, cut_amts):
            current_aum[pm] = max(current_aum[pm] - amt, floors[pm])
        for pm, amt in zip(winners, gain_amts):
            current_aum[pm] += amt * scale

        # Fund-level net flow (subscriptions / redemptions).
        fund_total = sum(current_aum.values())
        net_flow   = fund_total * float(rng.normal(mean_bps, std_bps)) / 1e4
        if net_flow >= 0:
            per_w = net_flow / len(winners)
            for pm in winners:
                current_aum[pm] += per_w
        else:
            per_l = abs(net_flow) / len(losers)
            for pm in losers:
                current_aum[pm] = max(current_aum[pm] - per_l, floors[pm])

        for pm_id in pm_ids:
            rows.append({"date": month_end, "pm_id": pm_id, "pm_aum": current_aum[pm_id]})

    return pd.DataFrame(rows, columns=["date", "pm_id", "pm_aum"])


def generate_all(cfg: dict | None = None) -> dict[str, pd.DataFrame]:
    """Generate every table and write parquet files to ``data/``.

    Returns the dict of DataFrames (also useful for tests / notebooks).
    """
    cfg = cfg or load_config()
    rng = np.random.default_rng(cfg["seed"])
    dates = _business_dates(cfg["n_business_days"], cfg.get("calendar_start", "2025-01-02"))

    pods = pd.DataFrame(cfg["pods"])
    pms = pd.DataFrame(cfg["pms"])
    instruments = generate_instruments(cfg, rng)
    prices = generate_prices(cfg, instruments, dates, rng)
    positions = generate_positions(cfg, pms, instruments, prices, dates, rng)
    income    = generate_income(cfg, pms, dates, rng)
    aum_hist  = generate_aum_history(cfg, pms, prices, positions, dates, rng)

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
        "aum_history":        aum_hist,
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
