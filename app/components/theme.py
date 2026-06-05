"""Shared visual system: page config + scoped CSS.

The CSS only styles layout, cards, chips, and typography — every chart stays a
native Streamlit chart (``st.line_chart`` / ``st.area_chart`` / ``st.bar_chart``
/ ``st.scatter_chart``). Call :func:`setup_page` at the top of every page.
"""
from __future__ import annotations

import streamlit as st

# Palette (kept in sync with .streamlit/config.toml)
ACCENT = "#36CFC9"
ACCENT_2 = "#5B8DEF"
GOOD = "#3DD68C"
BAD = "#F4664A"
WARN = "#F2C94C"
MUTED = "#8A93A6"
CARD_BG = "#171B26"
CARD_BORDER = "#262C3A"

_CSS = f"""
<style>
/* ---- layout & typography ------------------------------------------------ */
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px; }}
h1, h2, h3 {{ letter-spacing: -0.01em; font-weight: 700; }}
h1 {{ font-size: 2.0rem; }}
section[data-testid="stSidebar"] {{ background: #0B0E14; border-right: 1px solid {CARD_BORDER}; }}

.page-title {{ font-size: 2.0rem; font-weight: 800; margin: 0 0 .15rem 0; }}
.page-sub {{ color: {MUTED}; font-size: 1.0rem; margin: 0 0 1.4rem 0; }}
.section-title {{ font-size: 1.15rem; font-weight: 700; margin: 1.4rem 0 .5rem 0;
                  border-left: 3px solid {ACCENT}; padding-left: .6rem; }}

/* ---- KPI cards ---------------------------------------------------------- */
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
             gap: 14px; margin: .2rem 0 1.0rem 0; }}
.kpi-card {{ background: linear-gradient(180deg, {CARD_BG} 0%, #12151E 100%);
             border: 1px solid {CARD_BORDER}; border-radius: 14px; padding: 16px 18px;
             box-shadow: 0 1px 0 rgba(255,255,255,0.02) inset, 0 6px 18px rgba(0,0,0,0.25); }}
.kpi-card .label {{ color: {MUTED}; font-size: .78rem; text-transform: uppercase;
                    letter-spacing: .06em; font-weight: 600; }}
.kpi-card .value {{ font-size: 1.7rem; font-weight: 800; margin-top: .25rem; line-height: 1.1; }}
.kpi-card .delta {{ font-size: .82rem; margin-top: .35rem; font-weight: 600; }}
.kpi-card.accent {{ border-color: {ACCENT}; box-shadow: 0 0 0 1px {ACCENT}33, 0 6px 18px rgba(0,0,0,.3); }}
.kpi-card.cost   {{ border-color: {BAD}55; }}
.delta.up   {{ color: {GOOD}; }}
.delta.down {{ color: {BAD}; }}
.delta.flat {{ color: {MUTED}; }}

/* ---- status chips (controls panel) ------------------------------------- */
.chip {{ display: inline-flex; align-items: center; gap: .4rem; padding: .28rem .7rem;
         border-radius: 999px; font-weight: 700; font-size: .8rem; }}
.chip.pass {{ background: {GOOD}1A; color: {GOOD}; border: 1px solid {GOOD}55; }}
.chip.fail {{ background: {BAD}1A;  color: {BAD};  border: 1px solid {BAD}66; }}
.recon-row {{ display: flex; justify-content: space-between; align-items: center;
              padding: .55rem .8rem; border: 1px solid {CARD_BORDER}; border-radius: 10px;
              background: {CARD_BG}; margin-bottom: 8px; }}
.recon-row .name {{ font-weight: 600; }}
.recon-row .diff {{ color: {MUTED}; font-size: .8rem; font-variant-numeric: tabular-nums; }}

.banner {{ border-radius: 12px; padding: .8rem 1rem; font-weight: 700; margin: .2rem 0 1rem 0; }}
.banner.ok   {{ background: {GOOD}14; color: {GOOD}; border: 1px solid {GOOD}55; }}
.banner.bad  {{ background: {BAD}14;  color: {BAD};  border: 1px solid {BAD}66; }}

.callout {{ background: {CARD_BG}; border: 1px solid {CARD_BORDER}; border-left: 3px solid {WARN};
            border-radius: 10px; padding: .9rem 1.1rem; margin: .4rem 0 1rem 0; }}
.callout .big {{ font-size: 1.5rem; font-weight: 800; color: {WARN}; }}
[data-testid="stMetricValue"] {{ font-weight: 800; }}
</style>
"""


def setup_page(title: str, icon: str = "📊") -> None:
    """Configure the Streamlit page and inject the shared CSS."""
    st.set_page_config(page_title=f"{title} · PM PnL", page_icon=icon, layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str) -> None:
    """Render the standard page title + subtitle block."""
    st.markdown(
        f'<div class="page-title">{title}</div><div class="page-sub">{subtitle}</div>',
        unsafe_allow_html=True,
    )


def section(title: str) -> None:
    """Render a styled section heading."""
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
