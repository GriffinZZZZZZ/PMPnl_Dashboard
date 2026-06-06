"""Fund Overview — CEO/investor landing page."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from app.components import charts
from app.components.controls import render_controls, render_date_filter
from app.components.kpi import fmt_money, fmt_pct, kpi_card, kpi_row, style_negative
from app.components.theme import colors, page_header, section, setup_page
from src.db import query
from src.engine import recon
from src.loader import compute_all, fund_nav_curve

setup_page("Fund Overview", "🏦")

# ---- Global date filter (sidebar) -------------------------------------------
bounds = query("SELECT MIN(date) as lo, MAX(date) as hi FROM eod_prices").iloc[0]
render_date_filter(bounds["lo"], bounds["hi"])
date_from = st.session_state.get("date_from")
date_to   = st.session_state.get("date_to")

results = compute_all(date_from=date_from, date_to=date_to)
pms, pods = results["pms"], results["pods"]

page_header("Fund Overview")

# ---- KPI row ----------------------------------------------------------------
gross     = results["fund_gross"]
trading   = results["fund_trading"]
nontrad   = results["fund_non_trading"]
net       = results["fund_net"]
eligible  = results["fund_eligible_pnl"]
comp      = results["total_comp"]
inv       = results["investor_net"]
cards = [
    kpi_card("AUM", fmt_money(results["aum"])),
    kpi_card("Gross PnL", fmt_money(gross), "trading + non-trading", "up" if gross >= 0 else "down"),
    kpi_card("Non-trading PnL", fmt_money(nontrad), "other income, one-off",
             "up" if nontrad >= 0 else "down"),
    kpi_card("Net PnL", fmt_money(net), "after trading costs", "up" if net >= 0 else "down"),
    kpi_card("Eligible PnL", fmt_money(eligible), "after overhead & capital charge",
             "up" if eligible >= 0 else "down"),
    kpi_card("Incentive Comp Accrued", fmt_money(comp),
             f"{fmt_pct(results['comp_expense_ratio'])} of eligible",
             "down", variant="cost"),
    kpi_card("Investor Net", fmt_money(inv), "eligible − comp",
             "up" if inv >= 0 else "down", variant="accent"),
]
kpi_row(cards)

# ---- Fund equity curve — Gross / Net / Eligible -----------------------------
section("Fund Equity Curve")
pm_net = results["pm_net_daily"]
daily_agg = pm_net.groupby("date", as_index=False)[["gross_pnl", "net_pnl", "eligible_pnl"]].sum()
daily_agg = daily_agg.sort_values("date")
curve = daily_agg.set_index("date").cumsum().rename(
    columns={"gross_pnl": "Gross", "net_pnl": "Net", "eligible_pnl": "Eligible"}
)
p = colors()
# Semantic colors: green=raw profit, blue=after trading costs, amber=after all overhead
charts.show_line(curve, key="fund_eq", height=330, y_title="Cumulative PnL (USD)",
                 series_colors=[p["good"], p["accent2"], p["warn"]])
nav = fund_nav_curve(pm_net, results["aum"])
st.caption(
    f"Gross / Net / Eligible PnL (drag to zoom). "
    f"NAV at period end: **{fmt_money(float(nav['NAV'].iloc[-1]))}** "
    f"(AUM {fmt_money(results['aum'])} + cumulative net PnL)."
)

# ---- All-PM PnL in time dimension -------------------------------------------
section("All Portfolio Managers — PnL Over Time")
metric_map = {"Gross PnL": "gross_pnl", "Net PnL": "net_pnl", "Eligible PnL": "eligible_pnl"}
metric_label = st.radio("Metric", list(metric_map.keys()), horizontal=True, key="pm_ts_metric")
col = metric_map[metric_label]
pm_name_map = pms.set_index("pm_id")["pm_name"].to_dict()
pivot = (
    pm_net.groupby(["date", "pm_id"])[col].sum()
    .unstack("pm_id")
    .sort_index()
    .cumsum()
    .rename(columns=pm_name_map)
)
pivot = pivot.reindex(sorted(pivot.columns), axis=1)
charts.show_line(pivot, key="home_pm_ts", y_title=f"Cumulative {metric_label} (USD)", height=380)
st.caption(f"Cumulative {metric_label} per PM over the selected period. Drag to zoom.")

# ---- Pod / PM leaderboard ---------------------------------------------------
section("Pod & PM Leaderboard")
comp_by_pm = results["total_comp_by_pm"].set_index("pm_id")["total_comp"]
net_by_pm  = pm_net.groupby("pm_id")["net_pnl"].sum()
elig_by_pm = pm_net.groupby("pm_id")["eligible_pnl"].sum()
spark = (results["payoff_daily"].sort_values("date").groupby("pm_id")["cum_net"]
         .apply(lambda s: list(s)[-63:]))

pod_name  = pods.set_index("pod_id")["pod_name"].to_dict()
team_name = {t["team_id"]: t["name"] for t in results["cfg"]["teams"]}

rank = pms.set_index("pm_id").copy()
rank["Pod"]  = rank["pod_id"].map(pod_name)
rank["Team"] = rank["team_id"].map(team_name)
rank["Net PnL ($M)"]     = (net_by_pm / 1e6)
rank["Eligible ($M)"]    = (elig_by_pm / 1e6)
rank["Comp ($M)"]        = (comp_by_pm / 1e6)
rank["Comp / Eligible"]  = (comp_by_pm / elig_by_pm).clip(lower=0, upper=1).fillna(0) * 100
rank["Trend (3mo)"]      = spark
rank = rank.reset_index().sort_values("Net PnL ($M)", ascending=False)
rank.insert(0, "PM", rank["pm_name"])
show = rank[["PM", "Pod", "Team", "Net PnL ($M)", "Eligible ($M)", "Comp ($M)", "Comp / Eligible", "Trend (3mo)"]]

st.dataframe(
    style_negative(show, subset=["Net PnL ($M)", "Eligible ($M)"]),
    hide_index=True,
    width="stretch",
    column_config={
        "Net PnL ($M)":    st.column_config.NumberColumn(format="$%.1fM"),
        "Eligible ($M)":   st.column_config.NumberColumn(format="$%.1fM"),
        "Comp ($M)":       st.column_config.NumberColumn(format="$%.1fM"),
        "Comp / Eligible": st.column_config.ProgressColumn(min_value=0.0, max_value=100.0, format="%.0f%%"),
        "Trend (3mo)":     st.column_config.LineChartColumn("Trend (3mo)", width="medium"),
    },
)
st.caption("Net / Eligible PnL and comp in $M. Trend = cumulative eligible over the last ~3 months.")

# ---- Controls & Reconciliation ----------------------------------------------
section("Controls & Reconciliation")
render_controls(recon.run_checks(results, results["cfg"]))
