"""Shared visual system — native theming + a thin layer of component CSS.

Colors, fonts, radius, chart palettes, and light/dark are configured natively in
`.streamlit/config.toml` (`[theme.light]` / `[theme.dark]`). Users switch theme
from the app settings menu. The only CSS here styles a few bespoke components
(KPI cards, section headers, status chips, callouts) and it reads Streamlit's
injected `--st-*` theme variables, so it adapts to light/dark automatically.

`colors()` mirrors the config palette in Python for the Altair charts and the
income-statement table, which need concrete color values keyed on the active mode.
"""
from __future__ import annotations

import streamlit as st

# Mirror of the config.toml palettes, for code that needs concrete values
# (Altair semantic colors, the HTML income-statement). Categorical chart colors
# are inherited natively via `chartCategoricalColors`, so they live only in config.
_COLORS = {
    "dark": {
        "bg": "#0F141C", "surface": "#161D29", "border": "#243044",
        "text": "#E7ECF5", "muted": "#8A94A8", "accent": "#4FD1C5", "accent2": "#6AA0FF",
        "good": "#3FB870", "bad": "#F2645A", "warn": "#E3B341",
        "scheme": ["#4FD1C5", "#F78C6B", "#E3B341", "#C792EA", "#86E1A0", "#E06C9F", "#6AA0FF", "#FF6B6B"],
    },
    "light": {
        "bg": "#F5F4EF", "surface": "#FFFFFF", "border": "#E3DFD5",
        "text": "#1C2430", "muted": "#6B7280", "accent": "#0E8A7D", "accent2": "#3A6FD8",
        "good": "#1F9D55", "bad": "#D64545", "warn": "#B9791B",
        "scheme": ["#0E8A7D", "#C2603F", "#B9791B", "#8A5BD6", "#2E9E6B", "#B0508A", "#3A6FD8", "#D64545"],
    },
}


def colors() -> dict:
    """Concrete palette for the active theme (defaults to dark if unknown)."""
    try:
        mode = st.context.theme.type or "dark"
    except Exception:
        mode = "dark"
    return _COLORS.get(mode, _COLORS["dark"])


# Thin component CSS — uses --st-* theme variables so it follows light/dark natively.
_CSS = """
<style>
/* ---- sidebar nav: bigger, cleaner ---------------------------------------- */
[data-testid="stSidebarNav"] { padding: .6rem 0; }
[data-testid="stSidebarNav"] a { font-size: .95rem !important; font-weight: 500;
  padding: .5rem 1rem; border-radius: 8px; margin: 2px .5rem; display: block;
  color: var(--st-text-color) !important; text-decoration: none !important;
  transition: background .15s; }
[data-testid="stSidebarNav"] a:hover { background: var(--st-secondary-background-color); }
[data-testid="stSidebarNav"] a[aria-current="page"] {
  background: var(--st-secondary-background-color);
  border-left: 3px solid var(--st-primary-color); font-weight: 700; }

.block-container { padding-top: 2.0rem; padding-bottom: 3rem; max-width: 1400px; }

.page-title { font-family: var(--st-heading-font); font-size: 2.1rem; font-weight: 600;
  letter-spacing: -0.01em; margin: 0 0 .15rem 0; color: var(--st-heading-color); }
.page-sub { color: var(--st-gray-color, #8A94A8); font-size: 1.0rem; margin: 0 0 1.3rem 0; }
.section-title { font-size: 1.08rem; font-weight: 700; letter-spacing: .01em;
  margin: 1.5rem 0 .5rem 0; border-left: 3px solid var(--st-primary-color); padding-left: .6rem;
  color: var(--st-text-color); }

.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px; margin: .2rem 0 1.0rem 0; }
.kpi-card { background: var(--st-secondary-background-color); border: 1px solid var(--st-border-color);
  border-radius: var(--st-base-radius, 12px); padding: 16px 18px; box-shadow: 0 6px 18px rgba(0,0,0,0.16); }
.kpi-card .label { color: var(--st-gray-color, #8A94A8); font-size: .74rem; text-transform: uppercase;
  letter-spacing: .08em; font-weight: 600; }
.kpi-card .value { font-family: var(--st-code-font); font-size: 1.7rem; font-weight: 600;
  margin-top: .3rem; line-height: 1.1; font-variant-numeric: tabular-nums; color: var(--st-text-color); }
.kpi-card .delta { font-size: .82rem; margin-top: .35rem; font-weight: 600; }
.kpi-card.accent { border-color: var(--st-primary-color); }
.kpi-card.cost { border-color: var(--st-red-color, #F2645A); }
.delta.up { color: var(--st-green-color, #3FB870); }
.delta.down { color: var(--st-red-color, #F2645A); }
.delta.flat { color: var(--st-gray-color, #8A94A8); }

.chip { display: inline-flex; align-items: center; gap: .4rem; padding: .26rem .7rem;
  border-radius: 999px; font-weight: 700; font-size: .78rem; }
.chip.pass { background: var(--st-green-background-color, rgba(63,184,112,.12)); color: var(--st-green-color, #3FB870); }
.chip.fail { background: var(--st-red-background-color, rgba(242,100,90,.12)); color: var(--st-red-color, #F2645A); }
.recon-row { display: flex; justify-content: space-between; align-items: center;
  padding: .55rem .85rem; border: 1px solid var(--st-border-color); border-radius: 10px;
  background: var(--st-secondary-background-color); margin-bottom: 8px; }
.recon-row .name { font-weight: 500; }
.recon-row .diff { color: var(--st-gray-color, #8A94A8); font-size: .8rem; font-family: var(--st-code-font);
  font-variant-numeric: tabular-nums; }
.banner { border-radius: 12px; padding: .8rem 1rem; font-weight: 700; margin: .2rem 0 1rem 0; }
.banner.ok { background: var(--st-green-background-color, rgba(63,184,112,.12)); color: var(--st-green-color, #3FB870); }
.banner.bad { background: var(--st-red-background-color, rgba(242,100,90,.12)); color: var(--st-red-color, #F2645A); }
.explain { color: var(--st-gray-color, #8A94A8); font-size: .86rem; margin: -.2rem 0 .7rem 0; }
.callout { background: var(--st-secondary-background-color); border: 1px solid var(--st-border-color);
  border-left: 3px solid var(--st-yellow-color, #E3B341); border-radius: 10px; padding: .9rem 1.1rem; margin: .4rem 0 1rem 0; }
.callout .big { font-family: var(--st-code-font); font-size: 1.5rem; font-weight: 600; color: var(--st-yellow-color, #E3B341); }
</style>
"""


def setup_page(title: str, icon: str = "📊") -> None:
    """Configure the page and inject the component CSS (theming is native)."""
    st.set_page_config(page_title=f"{title} · PM PnL", page_icon=icon, layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    """Render the standard page title (+ optional subtitle)."""
    sub = f'<div class="page-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(f'<div class="page-title">{title}</div>{sub}', unsafe_allow_html=True)


def section(title: str) -> None:
    """Render a styled section heading."""
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
