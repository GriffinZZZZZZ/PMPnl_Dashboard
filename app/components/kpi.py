"""Reusable formatted KPI cards and reconciliation chips (HTML, theme-styled)."""
from __future__ import annotations

import math

import streamlit as st


def fmt_money(x: float, unit: str = "auto") -> str:
    """Format a dollar amount compactly ($1.2M, $3.4B, etc.)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    sign = "-" if x < 0 else ""
    a = abs(x)
    if unit == "auto":
        if a >= 1e9:
            return f"{sign}${a/1e9:.2f}B"
        if a >= 1e6:
            return f"{sign}${a/1e6:.1f}M"
        if a >= 1e3:
            return f"{sign}${a/1e3:.0f}K"
        return f"{sign}${a:,.0f}"
    return f"{sign}${a:,.0f}"


def fmt_pct(x: float) -> str:
    """Format a fraction as a percentage, or em-dash if undefined."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x*100:.1f}%"


def kpi_card(label: str, value: str, delta: str | None = None,
             direction: str = "flat", variant: str = "") -> str:
    """Return the HTML for a single KPI card.

    Args:
        label: small uppercase caption.
        value: the big formatted value.
        delta: optional sub-line (e.g. "vs Gross").
        direction: ``up`` / ``down`` / ``flat`` -> colors the delta.
        variant: ``accent`` (highlight) or ``cost`` (red border) or "".
    """
    delta_html = (
        f'<div class="delta {direction}">{delta}</div>' if delta else ""
    )
    cls = f"kpi-card {variant}".strip()
    return (
        f'<div class="{cls}"><div class="label">{label}</div>'
        f'<div class="value">{value}</div>{delta_html}</div>'
    )


def kpi_row(cards: list[str]) -> None:
    """Render a responsive grid of KPI cards (list of ``kpi_card`` HTML strings)."""
    st.markdown('<div class="kpi-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)
