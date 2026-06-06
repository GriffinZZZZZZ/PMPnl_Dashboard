"""Pod & PM drill-down: equity curve, Gross→Net→Eligible waterfall, attribution, HWM/comp."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.components import charts
from app.components.controls import render_date_filter
from app.components.kpi import fmt_money, fmt_pct, kpi_card, kpi_row, style_negative
from app.components.theme import colors, page_header, section, setup_page
from src.db import query
from src.engine import attribution, costs
from src.loader import compute_all

setup_page("Pod & PM", "🔍")

bounds = query("SELECT MIN(date) as lo, MAX(date) as hi FROM eod_prices").iloc[0]
render_date_filter(bounds["lo"], bounds["hi"])
date_from = st.session_state.get("date_from")
date_to   = st.session_state.get("date_to")

results = compute_all(date_from=date_from, date_to=date_to)
pms, pods = results["pms"], results["pods"]
pm_net_daily = results["pm_net_daily"]
payoff = results["payoff_daily"]
pod_name  = pods.set_index("pod_id")["pod_name"].to_dict()
team_name = {t["team_id"]: t["name"] for t in results["cfg"]["teams"]}
pm_label  = pms.set_index("pm_id")["pm_name"].to_dict()

page_header("Pod & PM Drill-down", "Inspect any pod or PM: performance, cost bridge, attribution, and comp.")

# ---- selectors: pods + teams -----------------------------------------------
col1, col2 = st.columns(2)
pod_options = ["__ALL__"] + list(pods["pod_id"]) + [t["team_id"] for t in results["cfg"]["teams"]]

def _sel_label(sid):
    if sid == "__ALL__": return "All pods"
    if sid in pod_name:  return pod_name[sid]
    return team_name.get(sid, sid)

pod_id = col1.selectbox("Pod / Team", pod_options, format_func=_sel_label)

if pod_id == "__ALL__":
    pod_pms = pms
elif pod_id in pod_name:
    pod_pms = pms[pms["pod_id"] == pod_id]
else:
    pod_pms = pms[pms["team_id"] == pod_id]

pm_options = ["__ALL__"] + list(pod_pms["pm_id"])
pm_sel = col2.selectbox("PM", pm_options,
    format_func=lambda p: "All PMs in selection" if p == "__ALL__" else pm_label[p])

if pm_sel == "__ALL__":
    sel_pms = list(pod_pms["pm_id"])
    title   = _sel_label(pod_id)
else:
    sel_pms = [pm_sel]
    title   = pm_label[pm_sel]

sel_daily  = pm_net_daily[pm_net_daily["pm_id"].isin(sel_pms)]
sel_payoff = payoff[payoff["pm_id"].isin(sel_pms)]

# ---- KPI row ----------------------------------------------------------------
gross    = float(sel_daily["gross_pnl"].sum())
net      = float(sel_daily["net_pnl"].sum())
eligible = float(sel_daily["eligible_pnl"].sum())
comp     = float(results["total_comp_by_pm"].set_index("pm_id").loc[sel_pms, "total_comp"].sum())
cap      = float(pms.set_index("pm_id").loc[sel_pms, "pm_aum"].sum())
kpi_row([
    kpi_card("Allocated Capital", fmt_money(cap)),
    kpi_card("Gross PnL", fmt_money(gross), "before costs", "up" if gross >= 0 else "down"),
    kpi_card("Net PnL", fmt_money(net), "after trading costs", "up" if net >= 0 else "down"),
    kpi_card("Eligible PnL", fmt_money(eligible),
             f"{fmt_pct(eligible/cap if cap else 0)} on capital",
             "up" if eligible >= 0 else "down"),
    kpi_card("Incentive Comp", fmt_money(comp), "accrued liability", "down", variant="cost"),
])

# ---- equity curve — 3 tiers -------------------------------------------------
section(f"{title} — Equity Curve")
curve = sel_daily.groupby("date")[["gross_pnl", "net_pnl", "eligible_pnl"]].sum().sort_index().cumsum()
curve.columns = ["Gross", "Net", "Eligible"]
charts.show_line(curve, key="pod_eq", height=300, y_title="Cumulative PnL (USD)")

# ---- Gross → Net → Eligible → Investor bridge --------------------------------
section("Gross → Net → Eligible → Investor Bridge")
bridge   = costs.bridge_components(sel_daily, sel_pms)
investor = bridge["Eligible PnL"] - comp
steps = [
    ("Gross PnL",       bridge["Gross PnL"],      "total"),
    ("− Financing",     bridge["Financing"],       "delta"),
    ("− Borrow",        bridge["Borrow"],          "delta"),
    ("− Commission",    bridge["Commission"],      "delta"),
    ("− FX",            bridge["FX"],              "delta"),
    ("Net PnL",         bridge["Net PnL"],         "total"),
    ("− Center",        bridge["Center"],          "delta"),
    ("− Capital Charge",bridge["Capital Charge"],  "delta"),
    ("Eligible PnL",    bridge["Eligible PnL"],    "total"),
    ("− Comp",          -comp,                     "delta"),
    ("Investor Net",    investor,                  "total"),
]
left, right = st.columns([3, 2])
with left:
    st.altair_chart(charts.waterfall(steps, height=420), width="stretch")
with right:
    p = colors()
    rows_html = ""
    subtotals = {"Gross PnL", "Net PnL", "Eligible PnL", "Investor Net"}
    for label, value, kind in steps:
        bold   = "font-weight:700;" if label in subtotals else ""
        indent = "" if label in subtotals else "padding-left:1.2rem;"
        border = f"border-top:1px solid {p['border']};" if label in subtotals else ""
        color  = p["bad"] if value < 0 else p["text"]
        amt    = f"{'-' if value < 0 else ''}${abs(value):,.0f}"
        rows_html += (
            f'<tr style="{border}"><td style="{indent}{bold}padding:.32rem .6rem;color:{p["text"]};">{label}</td>'
            f'<td style="text-align:right;font-family:IBM Plex Mono,monospace;{bold}padding:.32rem .6rem;color:{color};">{amt}</td></tr>'
        )
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;font-size:.9rem;background:{p["surface"]};'
        f'border:1px solid {p["border"]};border-radius:10px;overflow:hidden;">{rows_html}</table>',
        unsafe_allow_html=True,
    )
st.caption("Net PnL = Gross − trading costs. Eligible PnL = Net − center − capital charge. Investor Net = Eligible − Comp.")

# ---- attribution ------------------------------------------------------------
section("Strategy & Position Attribution")
pf = results["position_frame"]
pf = pf[pf["pm_id"].isin(sel_pms)]
left, right = st.columns(2)
with left:
    by_strat = attribution.contribution_by(pf, results["instruments"], "strategy_tag")
    st.altair_chart(
        charts.bar(by_strat, "strategy_tag", "gross_pnl", diverging=True, height=340,
                   title="Gross PnL by Strategy", val_title="Gross PnL (USD)"),
        width="stretch",
    )
with right:
    st.markdown("**Top & Bottom PnL Positions** — held by, return, and PnL")
    posn = attribution.top_bottom_positions(pf, results["instruments"], pms, n=10)
    disp = posn.rename(columns={"ticker": "Ticker", "held_by": "Held By",
                                "gross_pnl": "Gross PnL", "position_return": "Return"})
    disp["Return"] = disp["Return"] * 100
    st.dataframe(
        style_negative(disp[["Ticker", "Held By", "Gross PnL", "Return"]], subset=["Gross PnL", "Return"]),
        hide_index=True, width="stretch",
        column_config={
            "Gross PnL": st.column_config.NumberColumn(format="$%.0f"),
            "Return":    st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

# ---- HWM vs cumulative eligible + accrued comp ------------------------------
section("High-Water Mark, Cumulative Eligible PnL & Accrued Comp")
st.markdown(
    '<div class="explain">'
    'Incentive comp accrues <b>only when cumulative eligible PnL creates a new high above the HWM</b>. '
    'Eligible PnL = Net PnL − center overhead − capital charge. '
    'While cumulative eligible is below the HWM — or below a loss carryforward — '
    'no new comp accrues (daily_comp = 0).'
    '</div>',
    unsafe_allow_html=True,
)
carry = float(payoff[payoff["pm_id"].isin(sel_pms)].groupby("pm_id")["loss_carryforward"].first().sum())
if carry > 0:
    st.markdown(f'<div class="callout">Loss carryforward: '
                f'<span class="big">{fmt_money(carry)}</span> — must be recovered before comp accrues.</div>',
                unsafe_allow_html=True)
hwm_df = sel_payoff.groupby("date")[["cum_net", "hwm", "accrued_comp"]].sum().sort_index()
c1, c2 = st.columns([2, 1])
with c1:
    cn = hwm_df[["cum_net", "hwm"]].rename(
        columns={"cum_net": "Cumulative Eligible", "hwm": "High-Water Mark"})
    charts.show_line(cn, key="pod_hwm", height=300, y_title="USD",
                     title="Cumulative Eligible vs High-Water Mark")
with c2:
    charts.show_area(hwm_df.rename(columns={"accrued_comp": "Accrued Comp"}), "Accrued Comp",
                     key="pod_accr", height=300, title="Accrued Comp Liability")
