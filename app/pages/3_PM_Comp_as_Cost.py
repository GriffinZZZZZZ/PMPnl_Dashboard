"""PM Comp as Cost — comp expense, accrued liability, netting risk, sensitivity."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from app.components import charts
from app.components.kpi import fmt_money, fmt_pct, kpi_card, kpi_row, style_negative
from app.components.theme import page_header, section, setup_page
from src.config import blended_payout_ratio
from src.loader import comp_liability_curve, compute_all

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
kpi_row([
    kpi_card("Total PM Comp", fmt_money(results["total_comp"]), "accrued liability", "down", variant="cost"),
    kpi_card("Comp / Net PnL", fmt_pct(results["comp_expense_ratio"]), "expense ratio", "flat"),
    kpi_card("Netting Cost", fmt_money(results["netting_cost"]), "comp on offset gains", "down", variant="cost"),
    kpi_card("Investor Net", fmt_money(results["investor_net"]), "after comp & center", "up", variant="accent"),
])

# ---- comp by pod / PM -------------------------------------------------------
section("Comp Expense by Pod & PM")
tiers = cfg.get("comp_tiers", [])
tier_txt = ", ".join(
    f"+{t['add_pp']*100:.0f}pp above ${t['upto']/1e6:.0f}M" if t.get("upto") else f"+{t['add_pp']*100:.0f}pp on the rest"
    for t in tiers if t["add_pp"] > 0
)
st.markdown(
    f'<div class="explain">Each PM has a contractual <b>base payout ratio</b>; a structural ladder adds '
    f'marginal points on larger profit ({tier_txt}). The <b>effective rate</b> is the realized blend.</div>',
    unsafe_allow_html=True,
)
comp_pm = results["total_comp_by_pm"].merge(pms[["pm_id", "name", "pod_id", "payout_ratio"]], on="pm_id")
comp_pm["Pod"] = comp_pm["pod_id"].map(pod_name)
eff = results["effective_payout_rates"].set_index("pm_id")["effective_payout_rate"]
net_by_pm = results["pm_net_daily"].groupby("pm_id")["net_pnl"].sum()
comp_pm["Effective Rate"] = comp_pm["pm_id"].map(eff)

left, right = st.columns(2)
with left:
    by_pod = comp_pm.groupby("Pod", as_index=False)["total_comp"].sum()
    st.altair_chart(charts.bar(by_pod, "Pod", "total_comp", color=None, height=340,
                    title="Comp Expense by Pod", val_title="Comp (USD)"), width="stretch")
with right:
    st.markdown("**By PM** — base ratio, effective rate, and comp")
    tbl = comp_pm.copy()
    tbl["Base Payout Ratio"] = tbl["payout_ratio"] * 100
    tbl["Effective Rate"] = tbl["Effective Rate"] * 100
    tbl["Comp ($M)"] = tbl["total_comp"] / 1e6
    show = tbl[["name", "Pod", "Base Payout Ratio", "Effective Rate", "Comp ($M)"]].rename(
        columns={"name": "PM"}).sort_values("Comp ($M)", ascending=False)
    st.dataframe(
        show, hide_index=True, width="stretch", height=340,
        column_config={
            "Base Payout Ratio": st.column_config.NumberColumn(format="%.0f%%"),
            "Effective Rate": st.column_config.NumberColumn(format="%.1f%%"),
            "Comp ($M)": st.column_config.NumberColumn(format="$%.1fM"),
        },
    )

# ---- accrued comp liability + share of PnL ---------------------------------
section("Accrued Comp Liability Over Time")
liab = comp_liability_curve(results["payoff_daily"], results["pm_net_daily"])
liab = liab.rename(columns={"comp": "Accrued Comp", "comp_pct_of_pnl": "Comp % of Net PnL"})
st.altair_chart(
    charts.dual_line(liab, "Accrued Comp", "Comp % of Net PnL", left_title="Accrued Comp (USD)",
                     right_title="Comp % of Net PnL", height=320),
    width="stretch",
)
st.caption("Red area = comp the fund has booked as a liability; teal line = that comp as a share of net PnL to date.")

# ---- netting risk -----------------------------------------------------------
section("Netting Risk")
st.markdown(
    f'<div class="callout">When one pod\'s gains are offset by another\'s losses, investors net less '
    f'but the fund still owes the winners. The fund pays <span class="big">'
    f'{fmt_money(results["netting_cost"])}</span> more comp than if it were charged on its single netted book.</div>',
    unsafe_allow_html=True,
)
netting_df = pd.DataFrame({
    "Basis": ["Comp actually owed (per-PM)", "Comp if netted as one book"],
    "USD": [results["total_comp"], results["hypothetical_netted_comp"]],
})
st.altair_chart(charts.bar(netting_df, "Basis", "USD", horizontal=True, sort_by_value=False,
                color=None, height=200, val_title="USD"), width="stretch")

# ---- payout ratio sensitivity ----------------------------------------------
section("Decision Tool — Payout Ratio Sensitivity")
st.caption("Move the slider to see how a fund-wide base payout ratio changes comp expense and investor net, live.")
ratio = st.slider("Fund-wide base payout ratio (override)", 0.05, 0.40, 0.18, 0.01)
scenario = compute_all(payout_ratio_override=ratio)

d_comp = scenario["total_comp"] - results["total_comp"]
d_inv = scenario["investor_net"] - results["investor_net"]
c1, c2, c3 = st.columns(3)
c1.metric("Scenario Total Comp", fmt_money(scenario["total_comp"]), fmt_money(d_comp), delta_color="inverse")
c2.metric("Scenario Investor Net", fmt_money(scenario["investor_net"]), fmt_money(d_inv))
c3.metric("Scenario Comp / Net", fmt_pct(scenario["comp_expense_ratio"]))

current = blended_payout_ratio(cfg)
sweep_ratios = [round(x / 100, 2) for x in range(5, 41, 1)]
sweep = pd.DataFrame({
    "payout_ratio": sweep_ratios,
    "Total Comp": [compute_all(payout_ratio_override=r)["total_comp"] for r in sweep_ratios],
    "Investor Net": [compute_all(payout_ratio_override=r)["investor_net"] for r in sweep_ratios],
}).set_index("payout_ratio")
st.altair_chart(
    charts.sweep_curve(sweep, "payout_ratio", current, height=320,
                       title="Comp & Investor Net vs Payout Ratio"),
    width="stretch",
)
st.caption(f"Dashed line marks the current capital-weighted base payout ratio ({current:.0%}). "
           "Comp rises and investor net falls as the payout ratio increases — the core finance trade-off.")
