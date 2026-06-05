"""Pod & PM drill-down: equity curve, Gross->Net bridge, attribution, HWM/comp."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from app.components.kpi import fmt_money, fmt_pct, kpi_card, kpi_row
from app.components.theme import page_header, section, setup_page
from src.engine import attribution, costs, economics
from src.loader import compute_all

setup_page("Pod & PM", "🔍")
results = compute_all()
pms, pods = results["pms"], results["pods"]
pm_net_daily = results["pm_net_daily"]
payoff = results["payoff_daily"]

page_header("Pod & PM Drill-down", "Inspect any pod or PM: performance, cost bridge, attribution, and comp.")

# ---- selectors --------------------------------------------------------------
pod_name = pods.set_index("pod_id")["name"].to_dict()
col1, col2 = st.columns(2)
pod_id = col1.selectbox("Pod", pods["pod_id"], format_func=lambda p: pod_name[p])
pod_pms = pms[pms["pod_id"] == pod_id]
pm_choices = ["(All PMs in pod)"] + list(pod_pms["pm_id"])
pm_label = {pm: f"{row['name']}" for pm, row in pod_pms.set_index("pm_id").iterrows()}
pm_sel = col2.selectbox(
    "PM", pm_choices, format_func=lambda p: "All PMs in pod" if p.startswith("(") else pm_label[p]
)

if pm_sel.startswith("("):
    sel_pms = list(pod_pms["pm_id"])
    title = pod_name[pod_id]
else:
    sel_pms = [pm_sel]
    title = pm_label[pm_sel]

sel_daily = pm_net_daily[pm_net_daily["pm_id"].isin(sel_pms)]
sel_payoff = payoff[payoff["pm_id"].isin(sel_pms)]

# ---- KPI row ----------------------------------------------------------------
gross = float(sel_daily["gross_pnl"].sum())
net = float(sel_daily["net_pnl"].sum())
comp = float(results["total_comp_by_pm"].set_index("pm_id").loc[sel_pms, "total_comp"].sum())
cap = float(pms.set_index("pm_id").loc[sel_pms, "allocated_capital"].sum())
kpi_row(
    [
        kpi_card("Allocated Capital", fmt_money(cap)),
        kpi_card("Gross PnL", fmt_money(gross), "before costs", "up" if gross >= 0 else "down"),
        kpi_card("Net PnL", fmt_money(net), f"{fmt_pct(net/cap)} on capital", "up" if net >= 0 else "down"),
        kpi_card("PM Comp", fmt_money(comp), "accrued liability", "down", variant="cost"),
    ]
)

# ---- equity curve -----------------------------------------------------------
section(f"{title} — Equity Curve")
curve = sel_daily.groupby("date")[["gross_pnl", "net_pnl"]].sum().sort_index().cumsum()
curve.columns = ["Gross", "Net"]
st.line_chart(curve, height=300, color=["#5B8DEF", "#36CFC9"])

# ---- Gross -> Net -> Investor bridge ---------------------------------------
section("Gross → Net → Investor Bridge")
bridge = costs.bridge_components(sel_daily, sel_pms)
# Allocate center cost to the selected PMs (display only).
cc_alloc = economics.allocate_center_cost(results["cfg"], pms).set_index("pm_id")
center = float(cc_alloc.loc[sel_pms, "center_cost_alloc"].sum())
investor = bridge["Net PnL"] - comp - center
steps = {
    "Gross PnL": bridge["Gross PnL"],
    "− Financing": bridge["Financing"],
    "− Borrow": bridge["Borrow"],
    "− Commission": bridge["Commission"],
    "PM Net": bridge["Net PnL"],
    "− PM Comp": -comp,
    "− Center Cost": -center,
    "Investor Net": investor,
}
bridge_df = pd.DataFrame({"Component": list(steps), "USD": list(steps.values())}).set_index("Component")
st.bar_chart(bridge_df, height=320, color="#5B8DEF")
st.dataframe(
    bridge_df.reset_index(),
    hide_index=True,
    width="stretch",
    column_config={"USD": st.column_config.NumberColumn(format="$%.0f")},
)
st.caption("Costs and comp shown as negative deductions. PM Net and Investor Net are running subtotals.")

# ---- attribution ------------------------------------------------------------
section("Strategy & Position Attribution")
pf = results["position_frame"]
pf = pf[pf["pm_id"].isin(sel_pms)]
left, right = st.columns(2)
with left:
    st.markdown("**PnL by strategy**")
    by_strat = attribution.contribution_by(pf, results["instruments"], "strategy_tag")
    st.bar_chart(by_strat.set_index("strategy_tag"), height=300, color="#36CFC9")
with right:
    st.markdown("**Top contributors & detractors**")
    top = attribution.top_contributors(pf, results["instruments"], n=8)
    st.dataframe(
        top.rename(columns={"ticker": "Ticker", "gross_pnl": "Gross PnL"}),
        hide_index=True,
        width="stretch",
        column_config={
            "Gross PnL": st.column_config.BarChartColumn("Gross PnL", y_min=None, y_max=None)
        },
    )

# ---- HWM vs cumulative net + accrued comp ----------------------------------
section("High-Water Mark, Cumulative Net & Accrued Comp")
hwm_df = sel_payoff.groupby("date")[["cum_net", "hwm", "accrued_comp"]].sum().sort_index()
c1, c2 = st.columns([2, 1])
with c1:
    st.markdown("**Cumulative Net vs High-Water Mark**")
    st.line_chart(hwm_df[["cum_net", "hwm"]].rename(columns={"cum_net": "Cumulative Net", "hwm": "HWM"}),
                  height=280, color=["#36CFC9", "#F2C94C"])
with c2:
    st.markdown("**Accrued comp liability**")
    st.area_chart(hwm_df[["accrued_comp"]].rename(columns={"accrued_comp": "Accrued Comp"}),
                  height=280, color="#F4664A")
