"""Attribution: where PnL, cost, and loss come from; risk vs return."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from app.components.theme import page_header, section, setup_page
from src.engine import attribution
from src.loader import compute_all

setup_page("Attribution", "🧭")
results = compute_all()
pms, pods = results["pms"], results["pods"]
pm_net_daily = results["pm_net_daily"]
pf = results["position_frame"]
instruments = results["instruments"]

page_header("Attribution", "Decompose fund PnL by pod, strategy, and position — and see where costs and losses sit.")

# ---- PnL by pod / strategy --------------------------------------------------
section("PnL Attribution")
pod_name = pods.set_index("pod_id")["name"].to_dict()
left, right = st.columns(2)
with left:
    st.markdown("**Net PnL by Pod**")
    by_pod = attribution.pnl_by_pod(pm_net_daily, pms)
    by_pod["Pod"] = by_pod["pod_id"].map(pod_name)
    st.bar_chart(by_pod.set_index("Pod")[["net_pnl"]].rename(columns={"net_pnl": "Net PnL"}),
                 height=320, color="#36CFC9")
with right:
    st.markdown("**Gross PnL by Strategy**")
    by_strat = attribution.contribution_by(pf, instruments, "strategy_tag")
    st.bar_chart(by_strat.set_index("strategy_tag"), height=320, color="#5B8DEF")

# ---- PnL by asset class & position -----------------------------------------
left2, right2 = st.columns(2)
with left2:
    st.markdown("**Gross PnL by Asset Class**")
    by_ac = attribution.contribution_by(pf, instruments, "asset_class")
    st.bar_chart(by_ac.set_index("asset_class"), height=300, color="#5B8DEF")
with right2:
    st.markdown("**Top Contributors & Detractors (positions)**")
    top = attribution.top_contributors(pf, instruments, n=10)
    st.dataframe(
        top.rename(columns={"ticker": "Ticker", "gross_pnl": "Gross PnL"}),
        hide_index=True,
        width="stretch",
        column_config={"Gross PnL": st.column_config.BarChartColumn("Gross PnL")},
    )

# ---- cost attribution -------------------------------------------------------
section("Cost Attribution")
cost_df = attribution.cost_by_type(pm_net_daily)
st.bar_chart(cost_df.set_index("cost_type"), height=280, color="#F4664A")
st.caption("Total financing, borrow, and commission costs deducted from gross PnL across the fund.")

# ---- risk vs return scatter -------------------------------------------------
section("Risk vs Return by PM")
rr = attribution.risk_return(pm_net_daily, pms)
rr["Pod"] = rr["pod_id"].map(pod_name)
st.scatter_chart(
    rr, x="annual_vol", y="annual_return", color="Pod", size="annual_vol", height=380
)
st.caption("Each point is a PM: annualized return on capital (y) vs annualized volatility (x), colored by pod.")
