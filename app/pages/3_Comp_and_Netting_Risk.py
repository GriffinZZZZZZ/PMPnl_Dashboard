"""Incentive Compensation Accrual — comp expense, liability, netting risk, sensitivity."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.components import charts
from app.components.controls import render_date_filter
from app.components.kpi import fmt_money, fmt_pct, kpi_card, kpi_row
from app.components.theme import page_header, section, setup_page
from src.config import blended_payout_ratio
from src.db import query
from src.engine import attribution
from src.loader import comp_liability_curve, compute_all

setup_page("Incentive Compensation Accrual", "💰")
bounds = query("SELECT MIN(date) as lo, MAX(date) as hi FROM eod_prices").iloc[0]
render_date_filter(bounds["lo"], bounds["hi"])
date_from = st.session_state.get("date_from")
date_to   = st.session_state.get("date_to")
results = compute_all(date_from=date_from, date_to=date_to)
cfg = results["cfg"]
pms, pods = results["pms"], results["pods"]
pod_name = pods.set_index("pod_id")["pod_name"].to_dict()
team_name = {t["team_id"]: t["name"] for t in cfg["teams"]}

page_header(
    "Incentive Compensation Accrual",
    "Incentive comp is a GAAP liability that accrues daily against each PM's high-water mark. "
    "It is the fund's largest variable expense — asymmetric: the fund pays on gains, absorbs losses.",
)

# ---- KPI row ----------------------------------------------------------------
kpi_row([
    kpi_card("Total Accrued Comp", fmt_money(results["total_comp"]),
             "GAAP liability to date", "down", variant="cost"),
    kpi_card("Comp / Net PnL", fmt_pct(results["comp_expense_ratio"]), "expense ratio", "flat"),
    kpi_card("Netting Cost", fmt_money(results["netting_cost"]),
             "comp on offset gains", "down", variant="cost"),
    kpi_card("Investor Net", fmt_money(results["investor_net"]),
             "net PnL − comp", "up", variant="accent"),
])

# ---- comp by pod AND by team (two charts, no toggle) ----------------------
section("Accrued Incentive Comp by Pod & Team")
tiers = cfg.get("comp_tiers", [])
tier_txt = ", ".join(
    f"+{t['add_pp']*100:.0f}pp above ${t['upto']/1e6:.0f}M" if t.get("upto")
    else f"+{t['add_pp']*100:.0f}pp on the rest"
    for t in tiers if t["add_pp"] > 0
)
st.markdown(
    f'<div class="explain">Each PM has a contractual <b>base payout ratio</b> (% of eligible profit above HWM). '
    f'Structural ladder adds marginal points on larger profit ({tier_txt}). '
    f'The <b>effective rate</b> is the realized blend. Comp is paid on net PnL <em>after</em> '
    f'center cost pass-through.</div>',
    unsafe_allow_html=True,
)

comp_pm = results["total_comp_by_pm"].merge(
    pms[["pm_id", "pm_name", "pod_id", "team_id", "payout_ratio"]], on="pm_id"
)
comp_pm["Pod"] = comp_pm["pod_id"].map(pod_name)
comp_pm["Team"] = comp_pm["team_id"].map(team_name)
eff = results["effective_payout_rates"].set_index("pm_id")["effective_payout_rate"]
comp_pm["Effective Rate"] = comp_pm["pm_id"].map(eff)

c1, c2, c3 = st.columns(3)
with c1:
    by_pod = comp_pm.groupby("Pod", as_index=False)["total_comp"].sum()
    st.altair_chart(charts.bar(by_pod, "Pod", "total_comp", color=None, height=280,
                    title="By Strategy Pod", val_title="Accrued Comp (USD)"), width="stretch")
with c2:
    by_team = comp_pm.groupby("Team", as_index=False)["total_comp"].sum()
    st.altair_chart(charts.bar(by_team, "Team", "total_comp", color=None, height=280,
                    title="By Team", val_title="Accrued Comp (USD)"), width="stretch")
with c3:
    st.markdown("**By PM** — base rate, effective rate, comp")
    tbl = comp_pm.copy()
    tbl["Base Rate"] = tbl["payout_ratio"] * 100
    tbl["Eff. Rate"] = tbl["Effective Rate"] * 100
    tbl["Comp ($M)"] = tbl["total_comp"] / 1e6
    show = tbl[["pm_name", "Pod", "Base Rate", "Eff. Rate", "Comp ($M)"]].rename(
        columns={"pm_name": "PM"}).sort_values("Comp ($M)", ascending=False)
    st.dataframe(
        show, hide_index=True, width="stretch", height=280,
        column_config={
            "Base Rate": st.column_config.NumberColumn(format="%.0f%%"),
            "Eff. Rate": st.column_config.NumberColumn(format="%.1f%%"),
            "Comp ($M)": st.column_config.NumberColumn(format="$%.1fM"),
        },
    )

# ---- accrued comp liability + share of eligible PnL -------------------------
section("Accrued Comp Liability Over Time")
liab = comp_liability_curve(results["payoff_daily"], results["pm_net_daily"])
liab = liab.rename(columns={"comp": "Accrued Comp", "comp_pct_of_gross": "Comp % of Eligible PnL"})
charts.show_dual(liab, "Accrued Comp", "Comp % of Eligible PnL", key="comp_liab",
                 left_title="Accrued Comp (USD)", right_title="Comp % of Eligible PnL", height=320)
st.caption(
    "Red area = cumulative incentive comp booked as a GAAP liability. "
    "Teal line = comp as a share of cumulative eligible PnL (gross PnL used as denominator proxy). "
    "Comp accrues only when a PM creates a new high above their HWM."
)

# ---- netting risk time series -----------------------------------------------
section("Netting Risk Over Time")
st.markdown(
    f'<div class="callout">When Pod A wins and Pod B loses by the same amount, investors net zero — '
    f'but the fund still owes Pod A\'s comp. The cumulative extra comp the fund has paid '
    f'on gains that were offset by losses is currently '
    f'<span class="big">{fmt_money(results["netting_cost"])}</span>.</div>',
    unsafe_allow_html=True,
)
netting_ts = attribution.netting_cost_curve(
    results["payoff_daily"], results["pm_net_daily"], cfg
)
charts.show_line(
    netting_ts[["total_comp", "netting_cost"]].rename(
        columns={"total_comp": "Total Accrued Comp", "netting_cost": "Netting Cost"}
    ),
    key="netting_ts", height=280, y_title="USD",
    title="Cumulative Netting Cost vs Total Accrued Comp",
)
st.caption("Netting cost = comp actually paid minus what the fund would pay if all PMs were netted into one book.")

# ---- payout ratio sensitivity -----------------------------------------------
section("Decision Tool — Payout Ratio Sensitivity")
st.caption("Move the slider to see how a change in the fund-wide base payout ratio affects comp and investor net.")
ratio = st.slider("Fund-wide base payout ratio (override)", 0.05, 0.40, 0.18, 0.01)
scenario = compute_all(payout_ratio_override=ratio, date_from=date_from, date_to=date_to)

d_comp = scenario["total_comp"] - results["total_comp"]
d_inv  = scenario["investor_net"] - results["investor_net"]
c1, c2, c3 = st.columns(3)
c1.metric("Scenario Total Comp",    fmt_money(scenario["total_comp"]), fmt_money(d_comp), delta_color="inverse")
c2.metric("Scenario Investor Net",  fmt_money(scenario["investor_net"]), fmt_money(d_inv))
c3.metric("Scenario Comp / Eligible", fmt_pct(scenario["comp_expense_ratio"]))

current = blended_payout_ratio(cfg)
import pandas as pd
sweep_ratios = [round(x / 100, 2) for x in range(5, 41, 1)]
sweep = pd.DataFrame({
    "payout_ratio": sweep_ratios,
    "Total Comp":   [compute_all(payout_ratio_override=r, date_from=date_from, date_to=date_to)["total_comp"]   for r in sweep_ratios],
    "Investor Net": [compute_all(payout_ratio_override=r, date_from=date_from, date_to=date_to)["investor_net"] for r in sweep_ratios],
}).set_index("payout_ratio")
st.altair_chart(
    charts.sweep_curve(sweep, "payout_ratio", current, height=320,
                       title="Comp & Investor Net vs Payout Ratio"),
    width="stretch",
)
st.caption(f"Dashed line = current capital-weighted base payout ratio ({current:.0%}). Comp rises and investor net falls as the ratio increases.")
