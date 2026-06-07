"""Controls & Reconciliation panel renderer + global date range filter."""
from __future__ import annotations

import datetime

import pandas as pd
import streamlit as st

from src.engine.recon import Check, all_passed


def render_date_filter(first_date, last_date) -> None:
    """Render a YTD-defaulting date range selector in the sidebar.

    Stores selection in ``st.session_state["date_from"]`` / ``["date_to"]``.
    Must be called from each page after ``setup_page()``.

    Args:
        first_date: earliest date available in the dataset (str or Timestamp).
        last_date:  latest date available.
    """
    first = pd.Timestamp(first_date).date()
    last  = pd.Timestamp(last_date).date()
    ytd_start = datetime.date(last.year, 1, 1)
    # Clamp YTD start to the actual data range.
    ytd_start = max(ytd_start, first)

    # Initialize defaults on first load.
    if "date_from" not in st.session_state:
        st.session_state["date_from"] = str(ytd_start)
    if "date_to" not in st.session_state:
        st.session_state["date_to"] = str(last)

    with st.sidebar:
        st.markdown("**Analysis Period**")
        col1, col2 = st.columns(2)
        d_from = col1.date_input(
            "From", value=pd.Timestamp(st.session_state["date_from"]).date(),
            min_value=first, max_value=last, key="_df_from",
        )
        d_to = col2.date_input(
            "To", value=pd.Timestamp(st.session_state["date_to"]).date(),
            min_value=first, max_value=last, key="_df_to",
        )
        if d_from > d_to:
            st.warning("'From' must be before 'To' — reset to single day.", icon="⚠️")
            d_from = d_to
        st.session_state["date_from"] = str(d_from)
        st.session_state["date_to"]   = str(d_to)
        st.caption(f"YTD default: {ytd_start} → {last}")


def _fmt(x: float) -> str:
    return f"{x:,.2f}"


def render_controls(checks: list[Check]) -> None:
    """Render the reconciliation tie-outs as a green/red panel.

    All-green means Fund == Σ Pod == Σ PM, comp ties to the sum of PM payouts,
    and the investor-net identity holds — i.e. the numbers are trustworthy.
    """
    ok = all_passed(checks)
    banner_cls = "ok" if ok else "bad"
    banner_txt = (
        "✓ ALL CONTROLS PASS — numbers reconcile end-to-end"
        if ok
        else "✗ RECONCILIATION BREAK — investigate before trusting these numbers"
    )
    st.markdown(f'<div class="banner {banner_cls}">{banner_txt}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="explain">These are independent finance tie-outs: each row checks that one '
        'number equals the sum of its parts (e.g. the fund total equals every PM added up). '
        'All-green means the books add up and the figures on every page can be trusted.</div>',
        unsafe_allow_html=True,
    )

    rows = []
    for c in checks:
        chip = "pass" if c.passed else "fail"
        label = "PASS" if c.passed else "FAIL"
        rows.append(
            f'<div class="recon-row"><span class="name">{c.name}</span>'
            f'<span><span class="diff">Δ {_fmt(c.diff)}</span>&nbsp;&nbsp;'
            f'<span class="chip {chip}">● {label}</span></span></div>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True)
