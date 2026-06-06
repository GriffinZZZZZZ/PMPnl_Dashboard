"""Pod & PM drill-down: equity curve, Gross->Net waterfall, attribution, HWM/comp."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.components import charts
from app.components.kpi import fmt_money, fmt_pct, kpi_card, kpi_row, style_negative
from app.components.theme import active_palette, page_header, section, setup_page
from src.engine import attribution, costs, economics
from src.loader import compute_all

setup_page("Pod & PM", "🔍")
results = compute_all()
pms, pods = results["pms"], results["pods"]
pm_net_daily = results["pm_net_daily"]
payoff = results["payoff_daily"]
pod_name = pods.set_index("pod_id")["name"].to_dict()
pm_label = pms.set_index("pm_id")["name"].to_dict()

page_header("Pod & PM Drill-down", "Inspect any pod or PM: performance, cost bridge, attribution, and comp.")

# ---- selectors --------------------------------------------------------------
col1, col2 = st.columns(2)
pod_options = ["__ALL__"] + list(pods["pod_id"])
pod_id = col1.selectbox("Pod", pod_options,
                        format_func=lambda p: "All pods" if p == "__ALL__" else pod_name[p])
pod_pms = pms if pod_id == "__ALL__" else pms[pms["pod_id"] == pod_id]
pm_options = ["__ALL__"] + list(pod_pms["pm_id"])
pm_sel = col2.selectbox(
    "PM", pm_options,
    format_func=lambda p: ("All PMs" if pod_id == "__ALL__" else "All PMs in pod") if p == "__ALL__" else pm_label[p],
)

if pm_sel == "__ALL__":
    sel_pms = list(pod_pms["pm_id"])
    title = "All Pods" if pod_id == "__ALL__" else pod_name[pod_id]
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
kpi_row([
    kpi_card("Allocated Capital", fmt_money(cap)),
    kpi_card("Gross PnL", fmt_money(gross), "before costs", "up" if gross >= 0 else "down"),
    kpi_card("Net PnL", fmt_money(net), f"{fmt_pct(net/cap)} on capital", "up" if net >= 0 else "down"),
    kpi_card("PM Comp", fmt_money(comp), "accrued liability", "down", variant="cost"),
])

# ---- equity curve -----------------------------------------------------------
section(f"{title} — Equity Curve")
curve = sel_daily.groupby("date")[["gross_pnl", "net_pnl"]].sum().sort_index().cumsum()
curve.columns = ["Gross", "Net"]
st.altair_chart(charts.line(curve, height=300, y_title="Cumulative PnL (USD)"), width="stretch")

# ---- Gross -> Net -> Investor bridge (waterfall + income statement) ---------
section("Gross → Net → Investor Bridge")
bridge = costs.bridge_components(sel_daily, sel_pms)
cc_alloc = economics.allocate_center_cost(results["cfg"], pms).set_index("pm_id")
center = float(cc_alloc.loc[sel_pms, "center_cost_alloc"].sum())
investor = bridge["Net PnL"] - comp - center
steps = [
    ("Gross PnL", bridge["Gross PnL"], "total"),
    ("− Financing", bridge["Financing"], "delta"),
    ("− Borrow", bridge["Borrow"], "delta"),
    ("− Commission", bridge["Commission"], "delta"),
    ("PM Net", bridge["Net PnL"], "total"),
    ("− PM Comp", -comp, "delta"),
    ("− Center Cost", -center, "delta"),
    ("Investor Net", investor, "total"),
]
left, right = st.columns([3, 2])
with left:
    st.altair_chart(charts.waterfall(steps, height=340), width="stretch")
with right:
    # Income-statement-style table: indented deductions, bold subtotals, red negatives.
    p = active_palette()
    rows_html = ""
    subtotals = {"Gross PnL", "PM Net", "Investor Net"}
    for label, value, kind in steps:
        bold = "font-weight:700;" if label in subtotals else ""
        indent = "" if label in subtotals else "padding-left:1.2rem;"
        border = f"border-top:1px solid {p['border']};" if label in subtotals else ""
        color = p["bad"] if value < 0 else p["text"]
        amt = f"{'-' if value < 0 else ''}${abs(value):,.0f}"
        rows_html += (
            f'<tr style="{border}"><td style="{indent}{bold}padding:.32rem .6rem;color:{p["text"]};">{label}</td>'
            f'<td style="text-align:right;font-family:IBM Plex Mono,monospace;{bold}padding:.32rem .6rem;color:{color};">{amt}</td></tr>'
        )
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;font-size:.9rem;background:{p["surface"]};'
        f'border:1px solid {p["border"]};border-radius:10px;overflow:hidden;">{rows_html}</table>',
        unsafe_allow_html=True,
    )
st.caption("Costs and comp are deductions (negative). PM Net and Investor Net are running subtotals.")

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
    st.markdown("**Top & Bottom Positions** — held by, return, and PnL")
    posn = attribution.top_bottom_positions(pf, results["instruments"], pms, n=10)
    disp = posn.rename(columns={"ticker": "Ticker", "held_by": "Held By",
                                "gross_pnl": "Gross PnL", "position_return": "Return"})
    disp["Return"] = disp["Return"] * 100
    st.dataframe(
        style_negative(disp[["Ticker", "Held By", "Gross PnL", "Return"]], subset=["Gross PnL", "Return"]),
        hide_index=True, width="stretch",
        column_config={
            "Gross PnL": st.column_config.NumberColumn(format="$%.0f"),
            "Return": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

# ---- HWM vs cumulative net + accrued comp ----------------------------------
section("High-Water Mark, Cumulative Net & Accrued Comp")
st.markdown(
    '<div class="explain">Comp accrues <b>only on new highs above the high-water mark</b> (HWM). '
    'While cumulative net sits below the HWM, no new comp is earned. A PM carrying a prior-year loss '
    'must first earn it back before any comp accrues.</div>',
    unsafe_allow_html=True,
)
carry = float(payoff[payoff["pm_id"].isin(sel_pms)].groupby("pm_id")["loss_carryforward"].first().sum())
if carry > 0:
    st.markdown(f'<div class="callout">Prior-year loss carryforward to recover first: '
                f'<span class="big">{fmt_money(carry)}</span></div>', unsafe_allow_html=True)
hwm_df = sel_payoff.groupby("date")[["cum_net", "hwm", "accrued_comp"]].sum().sort_index()
c1, c2 = st.columns([2, 1])
with c1:
    cn = hwm_df[["cum_net", "hwm"]].rename(columns={"cum_net": "Cumulative Net", "hwm": "High-Water Mark"})
    st.altair_chart(charts.line(cn, height=300, y_title="USD", title="Cumulative Net vs High-Water Mark"),
                    width="stretch")
with c2:
    st.altair_chart(charts.area(hwm_df.rename(columns={"accrued_comp": "Accrued Comp"}), "Accrued Comp",
                                height=300, title="Accrued Comp Liability"), width="stretch")
