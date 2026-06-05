"""Fund Overview — the CEO/investor landing page.

Narrative: how finance turns PM profit into the fund's true cost and the
investor's true return, with a live controls panel proving it reconciles.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable when launched via `streamlit run app/Home.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from app.components.controls import render_controls
from app.components.kpi import fmt_money, fmt_pct, kpi_card, kpi_row
from app.components.theme import page_header, section, setup_page
from src.engine import recon
from src.loader import compute_all, fund_equity_curve

setup_page("Fund Overview", "🏦")
results = compute_all()
pms, pods = results["pms"], results["pods"]

page_header(
    "Fund Overview",
    "How finance turns PM trading profit into the fund's true cost and the investor's true return.",
)

# ---- KPI row ----------------------------------------------------------------
gross, net = results["fund_gross"], results["fund_net"]
comp, inv = results["total_comp"], results["investor_net"]
cards = [
    kpi_card("AUM", fmt_money(results["aum"])),
    kpi_card("Gross PnL (YTD)", fmt_money(gross), "before costs & comp", "up" if gross >= 0 else "down"),
    kpi_card("Net PnL (YTD)", fmt_money(net), "after trading costs", "up" if net >= 0 else "down"),
    kpi_card("PM Comp Expense", fmt_money(comp), f"{fmt_pct(results['comp_expense_ratio'])} of net",
             "down", variant="cost"),
    kpi_card("Investor Net", fmt_money(inv), "what LPs keep", "up" if inv >= 0 else "down",
             variant="accent"),
]
kpi_row(cards)

# ---- Fund equity curve ------------------------------------------------------
section("Fund Equity Curve — Gross vs Net")
curve = fund_equity_curve(results["pm_net_daily"])
st.line_chart(curve, height=320, color=["#5B8DEF", "#36CFC9"])
st.caption(
    "The gap between Gross and Net is the Gross→Net bridge: financing, borrow, and commission costs."
)

# ---- Pod / PM ranking -------------------------------------------------------
section("Pod & PM Leaderboard")
payoff = results["payoff_daily"]
comp_by_pm = results["total_comp_by_pm"].set_index("pm_id")["total_comp"]
net_by_pm = results["pm_net_daily"].groupby("pm_id")["net_pnl"].sum()

# Cumulative-net sparkline values per PM (ordered by date).
spark = (
    payoff.sort_values("date").groupby("pm_id")["cum_net"].apply(list)
)
pod_name = pods.set_index("pod_id")["name"]
rank = pms.set_index("pm_id").copy()
rank["Pod"] = rank["pod_id"].map(pod_name)
rank["Net PnL"] = net_by_pm
rank["Comp"] = comp_by_pm
rank["Comp / Net"] = (rank["Comp"] / rank["Net PnL"]).clip(lower=0, upper=1).fillna(0)
rank["Trend"] = spark
rank = rank.reset_index().sort_values("Net PnL", ascending=False)
rank.insert(0, "PM", rank["name"])

st.dataframe(
    rank[["PM", "Pod", "Net PnL", "Comp", "Comp / Net", "Trend"]],
    hide_index=True,
    width="stretch",
    column_config={
        "Net PnL": st.column_config.NumberColumn(format="$%.0f"),
        "Comp": st.column_config.NumberColumn(format="$%.0f"),
        "Comp / Net": st.column_config.ProgressColumn(
            "Comp / Net", min_value=0.0, max_value=1.0, format="%.0f%%"
        ),
        "Trend": st.column_config.LineChartColumn("Cumulative Net", y_min=None, y_max=None),
    },
)

# ---- Controls & Reconciliation ---------------------------------------------
section("Controls & Reconciliation")
st.caption(
    "Independent finance tie-outs. All-green means every number on every page reconciles end-to-end."
)
render_controls(recon.run_checks(results, results["cfg"]))
