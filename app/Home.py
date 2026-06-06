"""Fund Overview — CEO/investor landing page."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from app.components import charts
from app.components.controls import render_controls
from app.components.kpi import fmt_money, fmt_pct, kpi_card, kpi_row, style_negative
from app.components.theme import page_header, section, setup_page
from src.engine import recon
from src.loader import compute_all, fund_equity_curve, fund_nav_curve

setup_page("Fund Overview", "🏦")
results = compute_all()
pms, pods = results["pms"], results["pods"]

page_header("Fund Overview")

# ---- KPI row ----------------------------------------------------------------
gross, net = results["fund_gross"], results["fund_net"]
comp, inv = results["total_comp"], results["investor_net"]
cards = [
    kpi_card("AUM", fmt_money(results["aum"])),
    kpi_card("Gross PnL (YTD)", fmt_money(gross), "before costs & comp", "up" if gross >= 0 else "down"),
    kpi_card("Net PnL (YTD)", fmt_money(net), "after all costs incl. center", "up" if net >= 0 else "down"),
    kpi_card("Incentive Comp Accrued", fmt_money(comp), f"{fmt_pct(results['comp_expense_ratio'])} of net",
             "down", variant="cost"),
    kpi_card("Investor Net", fmt_money(inv), "net − comp", "up" if inv >= 0 else "down",
             variant="accent"),
]
kpi_row(cards)

# ---- Fund equity curve + NAV ------------------------------------------------
section("Fund Equity Curve & NAV")
curve = fund_equity_curve(results["pm_net_daily"])
nav = fund_nav_curve(results["pm_net_daily"], results["aum"])
# Show Gross, Net PnL on primary; NAV on a wide second axis via dual approach.
# We render as show_line with Gross + Net; NAV is too different in scale to overlay cleanly
# so we provide it as a separate metric line and caption.
charts.show_line(curve, key="fund_eq", height=330, y_title="Cumulative PnL (USD)")
st.caption(
    f"Gross vs Net PnL (drag to zoom). "
    f"NAV at year-end: **{fmt_money(float(nav['NAV'].iloc[-1]))}** "
    f"(initial AUM {fmt_money(results['aum'])} + cumulative net PnL)."
)

# ---- Pod / PM leaderboard — show both Pod and Team columns ------------------
section("Pod & PM Leaderboard")
comp_by_pm = results["total_comp_by_pm"].set_index("pm_id")["total_comp"]
net_by_pm = results["pm_net_daily"].groupby("pm_id")["net_pnl"].sum()
spark = (results["payoff_daily"].sort_values("date").groupby("pm_id")["cum_net"]
         .apply(lambda s: list(s)[-63:]))

pod_name = pods.set_index("pod_id")["pod_name"].to_dict()
team_name = {t["team_id"]: t["name"] for t in results["cfg"]["teams"]}

rank = pms.set_index("pm_id").copy()
rank["Pod"] = rank["pod_id"].map(pod_name)
rank["Team"] = rank["team_id"].map(team_name)
rank["Net PnL ($M)"] = (net_by_pm / 1e6)
rank["Comp ($M)"] = (comp_by_pm / 1e6)
rank["Comp / Net"] = (comp_by_pm / net_by_pm).clip(lower=0, upper=1).fillna(0) * 100
rank["Trend (3mo)"] = spark
rank = rank.reset_index().sort_values("Net PnL ($M)", ascending=False)
rank.insert(0, "PM", rank["pm_name"])
show = rank[["PM", "Pod", "Team", "Net PnL ($M)", "Comp ($M)", "Comp / Net", "Trend (3mo)"]]

st.dataframe(
    style_negative(show, subset=["Net PnL ($M)"]),
    hide_index=True,
    width="stretch",
    column_config={
        "Net PnL ($M)": st.column_config.NumberColumn(format="$%.1fM"),
        "Comp ($M)": st.column_config.NumberColumn(format="$%.1fM"),
        "Comp / Net": st.column_config.ProgressColumn(min_value=0.0, max_value=100.0, format="%.0f%%"),
        "Trend (3mo)": st.column_config.LineChartColumn("Trend (3mo)", width="medium"),
    },
)
st.caption("Net PnL and comp in $M. Trend = cumulative net over the last ~3 months. Losses shown in red.")

# ---- Controls & Reconciliation ---------------------------------------------
section("Controls & Reconciliation")
render_controls(recon.run_checks(results, results["cfg"]))
