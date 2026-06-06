"""Attribution: where PnL, cost, and loss come from; risk vs return."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import altair as alt
import streamlit as st

from app.components import charts
from app.components.kpi import fmt_pct, style_negative
from app.components.theme import page_header, section, setup_page
from src.engine import attribution
from src.loader import compute_all

setup_page("Attribution", "🧭")
results = compute_all()
pms, pods = results["pms"], results["pods"]
pm_net_daily = results["pm_net_daily"]
pf = results["position_frame"]
instruments = results["instruments"]
aum = results["aum"]
pod_name = pods.set_index("pod_id")["name"].to_dict()
team_name = {t["team_id"]: t["name"] for t in results["cfg"]["teams"]}

page_header("Attribution", "Decompose fund PnL by pod, strategy, and position — and see where costs and losses sit.")

# ---- PnL / Return attribution ----------------------------------------------
section("PnL Attribution")
c1, c2 = st.columns(2)
grouping = c1.radio("Pod taxonomy", ["Strategy Pod", "Team"], horizontal=True)
metric = c2.radio("Metric", ["PnL", "Return"], horizontal=True)
key = "pod_id" if grouping == "Strategy Pod" else "team_id"
names = pod_name if key == "pod_id" else team_name

left, right = st.columns(2)
with left:
    grp = attribution.pnl_by_group(pm_net_daily, pms, key)
    grp["label"] = grp[key].map(names)
    if metric == "PnL":
        st.altair_chart(charts.bar(grp, "label", "net_pnl", diverging=True, height=340,
                        title=f"Net PnL by {grouping}", val_title="Net PnL (USD)"), width="stretch")
    else:
        st.altair_chart(charts.bar(grp, "label", "return_on_capital", diverging=True, height=340,
                        fmt=".1%", title=f"Return on Capital by {grouping}", val_title="Return"),
                        width="stretch")
with right:
    strat = attribution.contribution_by(pf, instruments, "strategy_tag", aum=aum)
    if metric == "PnL":
        st.altair_chart(charts.bar(strat, "strategy_tag", "gross_pnl", diverging=True, height=340,
                        title="Gross PnL by Strategy", val_title="Gross PnL (USD)"), width="stretch")
    else:
        st.altair_chart(charts.bar(strat, "strategy_tag", "return_on_aum", diverging=True, height=340,
                        fmt=".2%", title="Contribution to Fund Return by Strategy", val_title="Return on AUM"),
                        width="stretch")

left2, right2 = st.columns(2)
with left2:
    ac = attribution.contribution_by(pf, instruments, "asset_class", aum=aum)
    valcol, vt, fmt = ("gross_pnl", "Gross PnL (USD)", "~s") if metric == "PnL" else \
        ("return_on_aum", "Return on AUM", ".2%")
    st.altair_chart(charts.bar(ac, "asset_class", valcol, diverging=True, height=340,
                    title="By Asset Class", val_title=vt, fmt=fmt), width="stretch")
with right2:
    st.markdown("**Top & Bottom Positions** — held by, return, and PnL")
    posn = attribution.top_bottom_positions(pf, instruments, pms, n=10)
    disp = posn.rename(columns={"ticker": "Ticker", "held_by": "Held By",
                                "gross_pnl": "Gross PnL", "position_return": "Return"})
    disp["Return"] = disp["Return"] * 100
    st.dataframe(
        style_negative(disp[["Ticker", "Held By", "Gross PnL", "Return"]], subset=["Gross PnL", "Return"]),
        hide_index=True, width="stretch", height=340,
        column_config={
            "Gross PnL": st.column_config.NumberColumn(format="$%.0f"),
            "Return": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

# ---- cost attribution -------------------------------------------------------
section("Cost Attribution")
total_cost = float(pm_net_daily[["financing", "borrow", "commission"]].sum().sum())
fund_cost_ratio = total_cost / results["fund_gross"] if results["fund_gross"] else float("nan")
m1, m2 = st.columns(2)
m1.metric("Total Trading Cost", f"${total_cost/1e6:,.1f}M")
m2.metric("Cost / Gross PnL", fmt_pct(fund_cost_ratio),
          help="Low ratio = performance comes from revenue, not just cost control.")

cost_key_label = st.radio("Break costs down by", ["Strategy Pod", "Team", "PM"], horizontal=True)
cost_key = {"Strategy Pod": "pod_id", "Team": "team_id", "PM": "pm_id"}[cost_key_label]
ctab = attribution.cost_table_by(pm_net_daily, pms, cost_key)
label_map = {"pod_id": pod_name, "team_id": team_name,
             "pm_id": pms.set_index("pm_id")["name"].to_dict()}[cost_key]
ctab["Name"] = ctab[cost_key].map(label_map)

left3, right3 = st.columns(2)
with left3:
    st.altair_chart(charts.bar(ctab, "Name", "total_cost", color=None, height=320,
                    title=f"Total Cost by {cost_key_label}", val_title="Total Cost (USD)"),
                    width="stretch")
with right3:
    st.markdown(f"**Cost detail by {cost_key_label}** (highest first)")
    show = ctab.rename(columns={"financing": "Financing", "borrow": "Borrow",
                                "commission": "Commission", "total_cost": "Total Cost",
                                "cost_ratio": "Cost / Gross"})
    show = show[["Name", "Financing", "Borrow", "Commission", "Total Cost", "Cost / Gross"]].copy()
    show["Cost / Gross"] = show["Cost / Gross"] * 100
    st.dataframe(
        show, hide_index=True, width="stretch", height=320,
        column_config={
            "Financing": st.column_config.NumberColumn(format="$%.0f"),
            "Borrow": st.column_config.NumberColumn(format="$%.0f"),
            "Commission": st.column_config.NumberColumn(format="$%.0f"),
            "Total Cost": st.column_config.NumberColumn(format="$%.0f"),
            "Cost / Gross": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

# ---- risk vs return scatter -------------------------------------------------
section("Risk vs Return by PM")
rr = attribution.risk_return(pm_net_daily, pms)
tooltip = [alt.Tooltip("name:N", title="PM"),
           alt.Tooltip("annual_return:Q", format=".1%", title="Return"),
           alt.Tooltip("annual_vol:Q", format=".1%", title="Volatility")]
st.altair_chart(
    charts.scatter(rr, "annual_vol", "annual_return", color_field="name", tooltip=tooltip,
                   height=400, x_title="Annualized Volatility", y_title="Annualized Return on Capital"),
    width="stretch",
)
st.caption("Each point is a PM, one color each. Up-and-left is better (more return per unit of risk).")
