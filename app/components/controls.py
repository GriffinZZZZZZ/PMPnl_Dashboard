"""Controls & Reconciliation panel renderer (drives the 'trustable' story)."""
from __future__ import annotations

import streamlit as st

from src.engine.recon import Check, all_passed


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
