"""Shared visual system: switchable palettes, page config, scoped CSS.

A small set of curated palettes (3 dark + 1 light) is exposed via a sidebar
selector. Colors are design tokens so both the CSS (cards, chips, headers) and
the Altair charts (`app/components/charts.py`) read from one source of truth.
Aesthetic: a refined financial terminal — elevated ink surfaces (never flat
#000), a metallic accent, editorial display type + tabular mono figures.
"""
from __future__ import annotations

import streamlit as st

# -----------------------------------------------------------------------------
# Palettes. Each is a dict of tokens; `scheme` is the categorical chart sequence.
# -----------------------------------------------------------------------------
PALETTES: dict[str, dict] = {
    "Midnight": {
        "mode": "dark",
        "bg": "#0F141C", "surface": "#161D29", "surface2": "#121925", "border": "#243044",
        "text": "#E7ECF5", "muted": "#8A94A8",
        "accent": "#4FD1C5", "accent2": "#6AA0FF",
        "good": "#3FB870", "bad": "#F2645A", "warn": "#E3B341",
        "scheme": ["#4FD1C5", "#6AA0FF", "#E3B341", "#C792EA", "#F78C6B", "#86E1A0", "#7FB3FF", "#E06C9F"],
    },
    "Graphite": {
        "mode": "dark",
        "bg": "#15161A", "surface": "#1E2026", "surface2": "#191A1F", "border": "#2E323B",
        "text": "#ECEAE3", "muted": "#969189",
        "accent": "#D4A24E", "accent2": "#8FB39B",
        "good": "#5FB37A", "bad": "#E06C5E", "warn": "#D9A441",
        "scheme": ["#D4A24E", "#8FB39B", "#C77B57", "#6E93B5", "#B0884E", "#A7C4A0", "#D89A6A", "#7FA0A8"],
    },
    "Slate": {
        "mode": "dark",
        "bg": "#0F1419", "surface": "#171E26", "surface2": "#131922", "border": "#242E3A",
        "text": "#E4E9F0", "muted": "#8794A4",
        "accent": "#7C9CF6", "accent2": "#57C6C2",
        "good": "#4CC38A", "bad": "#F26D6D", "warn": "#E6B450",
        "scheme": ["#7C9CF6", "#57C6C2", "#E6B450", "#B98CE0", "#EF8E6A", "#7FD6A4", "#6FB0F0", "#E07FA8"],
    },
    "Daylight": {
        "mode": "light",
        "bg": "#F5F4EF", "surface": "#FFFFFF", "surface2": "#FBFAF6", "border": "#E3DFD5",
        "text": "#1C2430", "muted": "#6B7280",
        "accent": "#0E8A7D", "accent2": "#3A6FD8",
        "good": "#1F9D55", "bad": "#D64545", "warn": "#B9791B",
        "scheme": ["#0E8A7D", "#3A6FD8", "#B9791B", "#8A5BD6", "#C2603F", "#2E9E6B", "#4A86C5", "#B0508A"],
    },
}
DEFAULT_THEME = "Midnight"

_FONTS = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Fraunces:opsz,wght@9..144,500;9..144,600&"
    "family=IBM+Plex+Sans:wght@400;500;600;700&"
    "family=IBM+Plex+Mono:wght@500;600&display=swap');"
)


def active_palette() -> dict:
    """Return the currently selected palette dict (defaults to ``DEFAULT_THEME``)."""
    return PALETTES.get(st.session_state.get("theme_choice", DEFAULT_THEME), PALETTES[DEFAULT_THEME])


def _css(p: dict) -> str:
    """Build the scoped stylesheet from the active palette tokens."""
    sans = "'IBM Plex Sans', -apple-system, system-ui, sans-serif"
    display = "'Fraunces', Georgia, serif"
    mono = "'IBM Plex Mono', ui-monospace, monospace"
    return f"""
<style>
{_FONTS}
:root {{ --bg:{p['bg']}; --surface:{p['surface']}; --surface2:{p['surface2']};
  --border:{p['border']}; --text:{p['text']}; --muted:{p['muted']};
  --accent:{p['accent']}; --accent2:{p['accent2']};
  --good:{p['good']}; --bad:{p['bad']}; --warn:{p['warn']}; }}

/* ---- app shell: drive bg + text from the active palette (runtime switch) -- */
.stApp, [data-testid="stAppViewContainer"] {{ background: var(--bg); color: var(--text); }}
[data-testid="stHeader"] {{ background: transparent; }}
section[data-testid="stSidebar"] {{ background: var(--surface2); border-right: 1px solid var(--border); }}
[data-testid="stAppViewContainer"], .stMarkdown, p, span, label, li {{ font-family: {sans}; color: var(--text); }}
.block-container {{ padding-top: 2.0rem; padding-bottom: 3rem; max-width: 1400px; }}
h1, h2, h3, .page-title {{ font-family: {display}; letter-spacing: -0.01em; font-weight: 600; color: var(--text); }}

.page-title {{ font-size: 2.1rem; margin: 0 0 .15rem 0; }}
.page-sub {{ color: var(--muted); font-size: 1.0rem; margin: 0 0 1.3rem 0; font-family: {sans}; }}
.section-title {{ font-family: {sans}; font-size: 1.08rem; font-weight: 700; letter-spacing: .01em;
  margin: 1.5rem 0 .5rem 0; border-left: 3px solid var(--accent); padding-left: .6rem; color: var(--text); }}

/* ---- KPI cards ---------------------------------------------------------- */
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px; margin: .2rem 0 1.0rem 0; }}
.kpi-card {{ background: linear-gradient(180deg, var(--surface) 0%, var(--surface2) 100%);
  border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px;
  box-shadow: 0 1px 0 rgba(255,255,255,0.03) inset, 0 8px 22px rgba(0,0,0,0.22); }}
.kpi-card .label {{ color: var(--muted); font-size: .74rem; text-transform: uppercase;
  letter-spacing: .08em; font-weight: 600; font-family: {sans}; }}
.kpi-card .value {{ font-family: {mono}; font-size: 1.7rem; font-weight: 600; margin-top: .3rem;
  line-height: 1.1; font-variant-numeric: tabular-nums; }}
.kpi-card .delta {{ font-size: .82rem; margin-top: .35rem; font-weight: 600; font-family: {sans}; }}
.kpi-card.accent {{ border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent)33, 0 8px 22px rgba(0,0,0,.28); }}
.kpi-card.cost   {{ border-color: var(--bad)66; }}
.delta.up   {{ color: var(--good); }}
.delta.down {{ color: var(--bad); }}
.delta.flat {{ color: var(--muted); }}

/* ---- status chips + banners (controls panel) --------------------------- */
.chip {{ display: inline-flex; align-items: center; gap: .4rem; padding: .26rem .7rem;
  border-radius: 999px; font-weight: 700; font-size: .78rem; font-family: {sans}; }}
.chip.pass {{ background: var(--good)1A; color: var(--good); border: 1px solid var(--good)55; }}
.chip.fail {{ background: var(--bad)1A;  color: var(--bad);  border: 1px solid var(--bad)66; }}
.recon-row {{ display: flex; justify-content: space-between; align-items: center;
  padding: .55rem .85rem; border: 1px solid var(--border); border-radius: 10px;
  background: var(--surface); margin-bottom: 8px; }}
.recon-row .name {{ font-weight: 500; font-family: {sans}; }}
.recon-row .diff {{ color: var(--muted); font-size: .8rem; font-family: {mono}; font-variant-numeric: tabular-nums; }}
.banner {{ border-radius: 12px; padding: .8rem 1rem; font-weight: 700; margin: .2rem 0 1rem 0; font-family: {sans}; }}
.banner.ok   {{ background: var(--good)14; color: var(--good); border: 1px solid var(--good)55; }}
.banner.bad  {{ background: var(--bad)14;  color: var(--bad);  border: 1px solid var(--bad)66; }}
.explain {{ color: var(--muted); font-size: .86rem; margin: -.2rem 0 .7rem 0; font-family: {sans}; }}

.callout {{ background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--warn);
  border-radius: 10px; padding: .9rem 1.1rem; margin: .4rem 0 1rem 0; }}
.callout .big {{ font-family: {mono}; font-size: 1.5rem; font-weight: 600; color: var(--warn); }}
[data-testid="stMetricValue"] {{ font-family: {mono}; font-weight: 600; }}
[data-testid="stDataFrame"] {{ font-variant-numeric: tabular-nums; }}
</style>
"""


def setup_page(title: str, icon: str = "📊") -> None:
    """Configure the page, render the theme selector, and inject palette CSS."""
    st.set_page_config(page_title=f"{title} · PM PnL", page_icon=icon, layout="wide")
    st.session_state.setdefault("theme_choice", DEFAULT_THEME)
    with st.sidebar:
        st.selectbox("Theme", list(PALETTES), key="theme_choice")
    st.markdown(_css(active_palette()), unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    """Render the standard page title (+ optional subtitle)."""
    sub = f'<div class="page-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(f'<div class="page-title">{title}</div>{sub}', unsafe_allow_html=True)


def section(title: str) -> None:
    """Render a styled section heading."""
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
