"""Attribution: where PnL, cost, and loss come from; risk vs return."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import altair as alt
import streamlit as st

from app.components import charts
from app.components.controls import render_date_filter
from app.components.kpi import fmt_money, fmt_pct, style_negative
from app.components.theme import page_header, section, setup_page
from src.db import query
from src.engine import attribution
from src.loader import compute_all

setup_page("Attribution", "🧭")
bounds = query("SELECT MIN(date) as lo, MAX(date) as hi FROM eod_prices").iloc[0]
render_date_filter(bounds["lo"], bounds["hi"])
date_from = st.session_state.get("date_from")
date_to   = st.session_state.get("date_to")
results = compute_all(date_from=date_from, date_to=date_to)
pms, pods = results["pms"], results["pods"]
pm_net_daily = results["pm_net_daily"]
pf = results["position_frame"]
instruments = results["instruments"]
aum = results["aum"]
pod_name = pods.set_index("pod_id")["pod_name"].to_dict()
team_name = {t["team_id"]: t["name"] for t in results["cfg"]["teams"]}

page_header("Attribution", "Decompose fund PnL by pod, strategy, and position — and see where costs and losses sit.")

# ---- PnL + Return attribution — two charts side by side, no toggle ----------
section("PnL Attribution")
c_left, c_right = st.columns(2)
with c_left:
    pod_grp = attribution.pnl_by_group(pm_net_daily, pms, "pod_id")
    pod_grp["label"] = pod_grp["pod_id"].map(pod_name)
    st.altair_chart(
        charts.bar_with_return(pod_grp, "label", "net_pnl", "return_on_capital",
                               height=340, title="Net PnL by Strategy Pod",
                               pnl_title="Net PnL (USD)", ret_title="Return on Capital"),
        width="stretch",
    )
with c_right:
    team_grp = attribution.pnl_by_group(pm_net_daily, pms, "team_id")
    team_grp["label"] = team_grp["team_id"].map(team_name)
    st.altair_chart(
        charts.bar_with_return(team_grp, "label", "net_pnl", "return_on_capital",
                               height=340, title="Net PnL by Team",
                               pnl_title="Net PnL (USD)", ret_title="Return on Capital"),
        width="stretch",
    )
st.caption("Bars = Net PnL (USD). Orange dots = return on allocated capital. Both on independent axes.")

left2, right2 = st.columns(2)
with left2:
    strat = attribution.contribution_by(pf, instruments, "strategy_tag", aum=aum)
    st.altair_chart(
        charts.bar_with_return(strat, "strategy_tag", "gross_pnl", "return_on_aum",
                               height=340, title="Gross PnL by Strategy",
                               pnl_title="Gross PnL (USD)", ret_title="Return on AUM"),
        width="stretch",
    )
with right2:
    ac = attribution.contribution_by(pf, instruments, "asset_class", aum=aum)
    st.altair_chart(
        charts.bar_with_return(ac, "asset_class", "gross_pnl", "return_on_aum",
                               height=340, title="Gross PnL by Asset Class",
                               pnl_title="Gross PnL (USD)", ret_title="Return on AUM"),
        width="stretch",
    )

# ---- Non-trading income (other non-recurring) -------------------------------
section("Non-trading Income by Category")
st.markdown(
    '<div class="explain">Instrument attribution above covers <b>Trading PnL</b> only '
    '(mark-to-market). <b>Non-trading PnL</b> — one-off items like tax reclaims, fee '
    'rebates, legal settlements, and corporate actions — is booked separately and added '
    'to reach Gross PnL.</div>',
    unsafe_allow_html=True,
)
income = results["eod_income"]
inc_left, inc_right = st.columns([3, 2])
with inc_left:
    by_cat = (income.groupby("category", as_index=False)["amount"].sum()
              .sort_values("amount", ascending=False))
    st.altair_chart(
        charts.bar(by_cat, "category", "amount", diverging=True, height=300,
                   title="Non-trading Income by Category", val_title="Amount (USD)"),
        width="stretch",
    )
with inc_right:
    st.markdown(
        f'<div class="callout">Trading PnL <span class="big">{fmt_money(results["fund_trading"])}</span> '
        f'+ Non-trading PnL <b>{fmt_money(results["fund_non_trading"])}</b> '
        f'= Gross PnL <b>{fmt_money(results["fund_gross"])}</b>.</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"{len(income):,} non-trading events across the selected period.")

# ---- Top / bottom PnL positions + concentration ----------------------------
section("Position Analysis")
pos_left, pos_right = st.columns(2)
with pos_left:
    st.markdown("**Top & Bottom 10 PnL Positions** — held by, return, and PnL")
    posn = attribution.top_bottom_positions(pf, instruments, pms, n=10)
    disp = posn.rename(columns={"ticker": "Ticker", "held_by": "Held By",
                                "gross_pnl": "Gross PnL", "position_return": "Return"})
    disp["Return"] = disp["Return"] * 100
    st.dataframe(
        style_negative(disp[["Ticker", "Held By", "Gross PnL", "Return"]], subset=["Gross PnL", "Return"]),
        hide_index=True, width="stretch", height=320,
        column_config={
            "Gross PnL": st.column_config.NumberColumn(format="$%.0f"),
            "Return": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )
with pos_right:
    st.markdown("**Top 10 Positions by NMV / AUM** — concentration risk")
    conc = attribution.concentration_table(pf, results["prices"], pms, aum, n=10)
    disp_c = conc.copy()
    disp_c["NMV"] = disp_c["nmv"]
    disp_c["NMV / AUM"] = disp_c["nmv_pct_aum"] * 100
    disp_c = disp_c.rename(columns={"ticker": "Ticker", "held_by": "Held By"})[
        ["Ticker", "Held By", "NMV", "NMV / AUM"]
    ]
    st.dataframe(
        disp_c, hide_index=True, width="stretch", height=320,
        column_config={
            "NMV": st.column_config.NumberColumn(format="$%.0f"),
            "NMV / AUM": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
st.caption("NMV = net market value (signed, last date). High NMV/AUM = concentrated position risk.")

# ---- cost attribution -------------------------------------------------------
section("Cost Attribution")
total_cost = float(pm_net_daily[["financing", "borrow", "commission",
                                  "fx", "center", "capital_charge"]].sum().sum())
fund_cost_ratio = total_cost / results["fund_gross"] if results["fund_gross"] else float("nan")
m1, m2 = st.columns(2)
m1.metric("Total Trading + Overhead Cost", f"${total_cost/1e6:,.1f}M",
          help="Includes financing, borrow, commission, FX, and center pass-through.")
m2.metric("Cost / Gross PnL", fmt_pct(fund_cost_ratio),
          help="Low ratio = performance comes from revenue, not just cost control.")

cost_key_label = st.radio("Break costs down by", ["Strategy Pod", "Team", "PM"], horizontal=True)
cost_key = {"Strategy Pod": "pod_id", "Team": "team_id", "PM": "pm_id"}[cost_key_label]
ctab = attribution.cost_table_by(pm_net_daily, pms, cost_key)
label_map = {"pod_id": pod_name, "team_id": team_name,
             "pm_id": pms.set_index("pm_id")["pm_name"].to_dict()}[cost_key]
ctab["Name"] = ctab[cost_key].map(label_map)

present_cost_cols = [c for c in ["financing", "borrow", "commission", "fx", "center", "capital_charge"]
                     if c in ctab.columns]
rename_map = {"financing": "Financing", "borrow": "Borrow", "commission": "Commission",
              "fx": "FX", "center": "Center", "capital_charge": "Capital Charge"}
display_cost_cols = [rename_map[c] for c in present_cost_cols]
ctab_display = ctab.rename(columns=rename_map)

c3, c4 = st.columns(2)
with c3:
    st.altair_chart(
        charts.stacked_cost_bar(ctab_display, "Name", display_cost_cols, "cost_ratio",
                                height=320, title=f"Cost Breakdown by {cost_key_label}",
                                ratio_title="Cost / Gross PnL"),
        width="stretch",
    )
with c4:
    st.markdown(f"**Cost detail by {cost_key_label}** — sorted by total cost")
    show_cols = ["Name"] + display_cost_cols + ["Total Cost", "Cost / Gross"]
    ctab_display["Total Cost"] = ctab_display["total_cost"]
    ctab_display["Cost / Gross"] = ctab_display["cost_ratio"] * 100
    charts.html_table(
        ctab_display[show_cols],
        money_cols=display_cost_cols + ["Total Cost"],
        pct_cols=["Cost / Gross"],
        na_str="n/a",
    )

# ---- risk vs return scatter -------------------------------------------------
section("Risk vs Return by PM")
rr = attribution.risk_return(pm_net_daily, pms)
tooltip = [
    alt.Tooltip("pm_name:N", title="PM"),
    alt.Tooltip("annual_return:Q", format=".1%", title="Return on Capital"),
    alt.Tooltip("annual_vol:Q", format=".1%", title="Annualized Volatility"),
    alt.Tooltip("sharpe:Q", format=".2f", title="Sharpe Ratio"),
]
st.altair_chart(
    charts.scatter(rr, "annual_vol", "annual_return",
                   color_field="pm_name", tooltip=tooltip,
                   height=400,
                   x_title="Annualized Volatility",
                   y_title="Annualized Return on Capital",
                   label_field="pm_name",
                   slope1_line=True),
    width="stretch",
)
st.caption("Each point is a PM. Dashed line = Sharpe ratio 1.0 (return = vol). Points above the line have Sharpe > 1. Hover for Sharpe ratio.")
