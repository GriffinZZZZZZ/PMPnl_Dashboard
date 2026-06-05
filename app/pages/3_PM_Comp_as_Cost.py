"""PM Comp as Cost — comp expense, accrued liability, netting risk, sensitivity."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from app.components.kpi import fmt_money, fmt_pct, kpi_card, kpi_row
from app.components.theme import page_header, section, setup_page
from src.loader import compute_all

setup_page("PM Comp as Cost", "💰")
results = compute_all()
cfg = results["cfg"]
pms, pods = results["pms"], results["pods"]
pod_name = pods.set_index("pod_id")["name"].to_dict()

page_header(
    "PM Comp as Cost",
    "PM compensation is the fund's largest, most volatile expense — and it is asymmetric: the fund pays for gains but eats the losses.",
)

# ---- comp expense KPI row ---------------------------------------------------
kpi_row(
    [
        kpi_card("Total PM Comp", fmt_money(results["total_comp"]), "accrued liability", "down", variant="cost"),
        kpi_card("Comp / Net PnL", fmt_pct(results["comp_expense_ratio"]), "expense ratio", "flat"),
        kpi_card("Netting Cost", fmt_money(results["netting_cost"]), "comp on offset gains", "down", variant="cost"),
        kpi_card("Investor Net", fmt_money(results["investor_net"]), "after comp & center", "up", variant="accent"),
    ]
)

# ---- comp by pod / PM -------------------------------------------------------
section("Comp Expense by Pod & PM")
comp_pm = results["total_comp_by_pm"].merge(pms[["pm_id", "name", "pod_id"]], on="pm_id")
comp_pm["Pod"] = comp_pm["pod_id"].map(pod_name)
left, right = st.columns(2)
with left:
    st.markdown("**By Pod**")
    by_pod = comp_pm.groupby("Pod", as_index=True)["total_comp"].sum().sort_values(ascending=False)
    st.bar_chart(by_pod.to_frame("Comp"), height=300, color="#F4664A")
with right:
    st.markdown("**By PM (with comp / net ratio)**")
    net_by_pm = results["pm_net_daily"].groupby("pm_id")["net_pnl"].sum()
    comp_pm["Net PnL"] = comp_pm["pm_id"].map(net_by_pm)
    comp_pm["Comp / Net"] = (comp_pm["total_comp"] / comp_pm["Net PnL"]).clip(0, 1).fillna(0)
    st.dataframe(
        comp_pm[["name", "Pod", "total_comp", "Comp / Net"]]
        .rename(columns={"name": "PM", "total_comp": "Comp"})
        .sort_values("Comp", ascending=False),
        hide_index=True,
        width="stretch",
        column_config={
            "Comp": st.column_config.NumberColumn(format="$%.0f"),
            "Comp / Net": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="%.0f%%"),
        },
    )

# ---- accrued comp liability over time --------------------------------------
section("Accrued Comp Liability Over Time")
accrued = results["payoff_daily"].groupby("date")["accrued_comp"].sum().sort_index()
st.area_chart(accrued.to_frame("Accrued Comp Liability"), height=300, color="#F4664A")
st.caption("The fund books comp as a GAAP liability that grows daily with PnL — not a year-end surprise.")

# ---- netting risk callout ---------------------------------------------------
section("Netting Risk")
st.markdown(
    f'<div class="callout">When one pod\'s gains are offset by another\'s losses, investors net less '
    f'but the fund still owes the winners. The fund pays <span class="big">'
    f'{fmt_money(results["netting_cost"])}</span> more comp than it would if charged on its single netted book.</div>',
    unsafe_allow_html=True,
)
netting_df = pd.DataFrame(
    {
        "Basis": ["Comp actually owed (per-PM)", "Comp if netted as one book"],
        "USD": [results["total_comp"], results["hypothetical_netted_comp"]],
    }
).set_index("Basis")
st.bar_chart(netting_df, height=240, color="#F2C94C")

# ---- payout_ratio sensitivity slider ---------------------------------------
section("Decision Tool — payout_ratio Sensitivity")
st.caption("Move the slider to see how a fund-wide payout ratio changes comp expense and investor net, live.")
ratio = st.slider("Fund-wide payout ratio (override)", 0.05, 0.40, 0.18, 0.01)
scenario = compute_all(payout_ratio_override=ratio)

d_comp = scenario["total_comp"] - results["total_comp"]
d_inv = scenario["investor_net"] - results["investor_net"]
c1, c2, c3 = st.columns(3)
c1.metric("Scenario Total Comp", fmt_money(scenario["total_comp"]), fmt_money(d_comp), delta_color="inverse")
c2.metric("Scenario Investor Net", fmt_money(scenario["investor_net"]), fmt_money(d_inv))
c3.metric("Scenario Comp / Net", fmt_pct(scenario["comp_expense_ratio"]))

# Sweep the payout ratio to show the trade-off curve.
sweep_ratios = [round(x / 100, 2) for x in range(5, 41, 1)]
sweep = pd.DataFrame(
    {
        "payout_ratio": sweep_ratios,
        "Total Comp": [compute_all(payout_ratio_override=r)["total_comp"] for r in sweep_ratios],
        "Investor Net": [compute_all(payout_ratio_override=r)["investor_net"] for r in sweep_ratios],
    }
).set_index("payout_ratio")
st.line_chart(sweep, height=320, color=["#F4664A", "#36CFC9"])
st.caption("Comp rises and investor net falls as the payout ratio increases — the core finance trade-off.")
