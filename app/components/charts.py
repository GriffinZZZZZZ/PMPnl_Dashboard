"""Theme-aware Altair chart builders shared by every page.

Altair (Vega-Lite, bundled with Streamlit, pure-Python) gives us angled axis
labels, tooltips, sorting, diverging colors, waterfalls, and dual-axis overlays.

Time-series charts (`show_line` / `show_area` / `show_dual`) are *rendered* here
(not just built) so they can add: a **drag-a-region zoom directly on the chart**
(Streamlit selection event → rescale + Reset), a **hover vertical guide line**,
and a **centered legend** below the plot. Categorical/scatter charts stay pure
builders that the page renders with ``st.altair_chart``.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from app.components.theme import colors

SANS = "IBM Plex Sans"
DISPLAY = "Fraunces"

# Vega-Lite category20 — 20 perceptually distinct colors for dense multi-series charts.
_CATEGORY20 = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
    "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5",
]


def _cfg(chart: alt.Chart, p: dict, *, legend_bottom: bool = True) -> alt.Chart:
    """Apply shared axis/legend/title/view styling from the palette."""
    return (
        chart.configure_view(strokeWidth=0, fill=None)
        .configure_axis(
            labelColor=p["muted"], titleColor=p["muted"], gridColor=p["border"],
            domainColor=p["border"], tickColor=p["border"], labelFont=SANS, titleFont=SANS,
            labelFontSize=11, titleFontSize=12, titleFontWeight=600, gridOpacity=0.5,
        )
        .configure_legend(
            labelColor=p["text"], titleColor=p["muted"], labelFont=SANS, titleFont=SANS,
            orient="bottom" if legend_bottom else "right",
            direction="horizontal" if legend_bottom else "vertical", symbolType="circle",
        )
        .configure_title(color=p["text"], font=DISPLAY, fontSize=14, anchor="start", fontWeight=600)
        .configure(background="transparent")
    )


# ---------------------------------------------------------------------------
# Time-series rendering helpers: drag-to-zoom + hover guide + centered legend
# ---------------------------------------------------------------------------
def _legend(items: list[tuple[str, str]]) -> None:
    """Render a centered legend (label + color swatch) below a chart."""
    chips = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:.4rem;margin:0 .8rem;">'
        f'<span style="width:12px;height:12px;border-radius:3px;background:{c};display:inline-block;"></span>'
        f'<span style="font-size:.82rem;color:var(--st-text-color);">{lbl}</span></span>'
        for lbl, c in items
    )
    st.markdown(f'<div style="text-align:center;margin:-.6rem 0 .4rem 0;">{chips}</div>',
                unsafe_allow_html=True)


def _zoom_filter(data: pd.DataFrame, x: str, key: str) -> pd.DataFrame:
    """Filter ``data`` to the stored zoom window (drag selection), if any.

    Zooming = filtering the data to the selected date range and letting the axis
    auto-scale. This is far more robust than constraining a temporal scale domain.
    """
    rng = st.session_state.get(f"zoom_{key}")
    if rng and len(rng) == 2:
        lo, hi = pd.Timestamp(float(rng[0]), unit="ms"), pd.Timestamp(float(rng[1]), unit="ms")
        return data[(data[x] >= lo) & (data[x] <= hi)]
    return data


def _apply_zoom(event, key: str, x: str) -> None:
    """Read the drag selection from a chart event, store it on change, offer Reset."""
    zkey = f"zoom_{key}"
    try:
        sel = (event.selection or {}).get("zoom") or {}
    except Exception:
        sel = {}
    rng = sel.get(x)
    if rng and len(rng) == 2:
        rng = [float(rng[0]), float(rng[1])]
        if st.session_state.get(zkey) != rng:
            st.session_state[zkey] = rng
            st.rerun()
    if st.session_state.get(zkey) is not None:
        st.button("⟲ Reset zoom", key=f"rz_{key}",
                  on_click=lambda: st.session_state.pop(zkey, None))


def _xenc(x: str):
    return alt.X(f"{x}:T", title=None, axis=alt.Axis(format="%b %Y"))


def _hover_zoom_params(x: str):
    nearest = alt.selection_point(nearest=True, on="pointerover", fields=[x], empty=False)
    zoom = alt.selection_interval(encodings=["x"], name="zoom")
    return nearest, zoom


@st.fragment
def show_line(
    df: pd.DataFrame, *, key: str, x: str = "date", y_title: str = "USD",
    height: int = 320, title: str | None = None,
    series_colors: list[str] | None = None,
) -> None:
    """Render a multi-series line chart with drag-zoom, hover guide, centered legend.

    Wrapped in ``@st.fragment`` so drag-to-zoom reruns only this chart, not the
    whole page.

    Args:
        series_colors: optional explicit color per series (same order as df columns).
            When None, theme scheme is used for ≤8 series; category20 for larger sets.
            IMPORTANT: always pass ``domain`` alongside ``range`` so Altair's
            alphabetical sort doesn't mis-map colors to lines (fixed here).
    """
    p = colors()
    data = df.reset_index() if x not in df.columns else df.copy()
    data = _zoom_filter(data, x, key)
    series = [c for c in data.columns if c != x]
    n = len(series)

    if series_colors is not None:
        palette = list(series_colors)[:n]
    elif n <= len(p["scheme"]):
        palette = p["scheme"][:n]
    else:
        palette = _CATEGORY20[:n]

    long = data.melt(id_vars=[x], value_vars=series, var_name="Series", value_name="value")
    xenc = _xenc(x)
    nearest, zoom = _hover_zoom_params(x)
    # Always legend=None here — the custom HTML _legend() below centers it reliably
    # across all series counts. Altair's built-in orient="bottom" is left-aligned and
    # consumes chart height, which breaks compact charts (height ≤ 220).
    color = alt.Color("Series:N", scale=alt.Scale(domain=series, range=palette), legend=None)
    base = alt.Chart(long)
    lines = base.mark_line(strokeWidth=2).encode(
        x=xenc, y=alt.Y("value:Q", title=y_title, axis=alt.Axis(titleAnchor="middle")), color=color,
        tooltip=[alt.Tooltip(f"{x}:T", title="Date"), alt.Tooltip("Series:N"),
                 alt.Tooltip("value:Q", format=",.0f", title="Value")],
    )
    selectors = base.mark_point().encode(x=xenc, opacity=alt.value(0)).add_params(nearest, zoom)
    points = lines.mark_point(size=55, filled=True).encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0)))
    rule = base.mark_rule(color=p["muted"], strokeDash=[4, 3], size=1).encode(
        x=xenc, opacity=alt.condition(nearest, alt.value(0.8), alt.value(0)))
    chart = _cfg(alt.layer(lines, selectors, points, rule).properties(height=height, title=title or ""), p)
    event = st.altair_chart(chart, key=key, on_select="rerun", selection_mode=["zoom"])
    _legend([(s, palette[i]) for i, s in enumerate(series)])
    _apply_zoom(event, key, x)


@st.fragment
def show_area(df: pd.DataFrame, val: str, *, key: str, x: str = "date", height: int = 280,
              color: str | None = None, y_title: str = "USD", title: str | None = None,
              y_zero: bool = True, y_fmt: str | None = None) -> None:
    """Render a single-series area with drag-zoom and a hover guide line.

    Args:
        y_zero: if False, y-axis domain is computed from the data range (5% padding each side),
            guaranteeing variation is visible even when the base value is large relative to swings.
        y_fmt: Vega-Lite/D3 format string for axis tick labels and tooltip (e.g. ".1%" for pct).
    """
    p = colors()
    c = color or p["bad"]
    data = df.reset_index() if x not in df.columns else df.copy()
    data = _zoom_filter(data, x, key)
    xenc = _xenc(x)
    nearest, zoom = _hover_zoom_params(x)
    base = alt.Chart(data)
    # Compute y-scale and, for all-positive data, an explicit area baseline.
    # Vega-Lite's mark_area always tries to fill to y=0. When y_zero=False and data
    # sits far above zero (e.g. AUM at 100 M), the scale gets silently extended down
    # to 0, pushing data to the very top with a huge blank region below.
    # Fix: for all-positive data, supply y2=datum(domain_lo) so the fill baseline
    # is the scale bottom rather than zero. For mixed/negative data (drawdown) zero
    # is already within the computed domain, so no explicit y2 is needed.
    y2_baseline = None
    if y_zero:
        y_scale = alt.Scale(zero=True)
    else:
        valid = data[val].dropna()
        if len(valid) > 0:
            d_min, d_max = float(valid.min()), float(valid.max())
            spread = (d_max - d_min) if d_max != d_min else max(abs(d_min) * 0.1, 1.0)
            domain_lo = d_min - spread * 0.05
            domain_hi = d_max + spread * 0.05
            y_scale = alt.Scale(zero=False, nice=False, domain=[domain_lo, domain_hi])
            if d_min > 0:          # all-positive series: pin baseline to domain floor
                y2_baseline = alt.datum(domain_lo)
        else:
            y_scale = alt.Scale(zero=False)
    axis_cfg = alt.Axis(titleAnchor="middle", format=y_fmt) if y_fmt else alt.Axis(titleAnchor="middle")
    tooltip_fmt = y_fmt or ",.0f"
    y2_enc = {"y2": y2_baseline} if y2_baseline is not None else {}
    area = base.mark_area(opacity=0.75, line={"color": c}, color=c).encode(
        x=xenc, y=alt.Y(f"{val}:Q", title=y_title, scale=y_scale, axis=axis_cfg),
        **y2_enc,
    )
    selectors = base.mark_point().encode(x=xenc, opacity=alt.value(0)).add_params(nearest, zoom)
    # Tooltip on the rule (vertical guide line) rather than the area mark:
    # area hover in Vega-Lite resolves x but often fails to resolve y field values.
    rule = base.mark_rule(color=p["muted"], strokeDash=[4, 3]).encode(
        x=xenc, opacity=alt.condition(nearest, alt.value(0.8), alt.value(0)),
        tooltip=[alt.Tooltip(f"{x}:T", title="Date"), alt.Tooltip(f"{val}:Q", format=tooltip_fmt)],
    )
    chart = _cfg(alt.layer(area, selectors, rule).properties(height=height, title=title or ""), p)
    event = st.altair_chart(chart, key=key, on_select="rerun", selection_mode=["zoom"])
    _apply_zoom(event, key, x)


@st.fragment
def show_stacked_area(
    df: pd.DataFrame, *, key: str, x: str = "date", y_title: str = "USD",
    height: int = 320, title: str | None = None,
    series_colors: list[str] | None = None,
) -> None:
    """Render a stacked area chart with drag-zoom, hover guide, and centered legend."""
    p = colors()
    data = df.reset_index() if x not in df.columns else df.copy()
    data = _zoom_filter(data, x, key)
    series = [c for c in data.columns if c != x]
    n = len(series)
    palette = list(series_colors)[:n] if series_colors else p["scheme"][:n]

    long = data.melt(id_vars=[x], value_vars=series, var_name="Series", value_name="value")
    xenc = _xenc(x)
    nearest, zoom = _hover_zoom_params(x)
    color = alt.Color("Series:N", scale=alt.Scale(domain=series, range=palette), legend=None)
    base = alt.Chart(long)
    areas = base.mark_area(opacity=0.82).encode(
        x=xenc,
        y=alt.Y("value:Q", stack="zero", title=y_title,
                axis=alt.Axis(titleAnchor="middle")),
        color=color,
        tooltip=[alt.Tooltip(f"{x}:T", title="Date"), alt.Tooltip("Series:N"),
                 alt.Tooltip("value:Q", format=",.0f", title="Value")],
    )
    selectors = base.mark_point().encode(x=xenc, opacity=alt.value(0)).add_params(nearest, zoom)
    rule = base.mark_rule(color=p["muted"], strokeDash=[4, 3], size=1).encode(
        x=xenc, opacity=alt.condition(nearest, alt.value(0.8), alt.value(0)))
    chart = _cfg(alt.layer(areas, selectors, rule).properties(height=height, title=title or ""), p)
    event = st.altair_chart(chart, key=key, on_select="rerun", selection_mode=["zoom"])
    _legend([(s, palette[i]) for i, s in enumerate(series)])
    _apply_zoom(event, key, x)


@st.fragment
def show_dual(df: pd.DataFrame, left: str, right: str, *, key: str, x: str = "date",
              left_title: str = "USD", right_title: str = "%", height: int = 300,
              title: str | None = None) -> None:
    """Render an area (left $) + line (right %) dual-axis chart with zoom + hover."""
    p = colors()
    data = df.reset_index() if x not in df.columns else df.copy()
    data = _zoom_filter(data, x, key)
    xenc = _xenc(x)
    nearest, zoom = _hover_zoom_params(x)
    base = alt.Chart(data)
    left_layer = base.mark_area(opacity=0.6, color=p["bad"], line={"color": p["bad"]}).encode(
        x=xenc, y=alt.Y(f"{left}:Q", title=left_title, axis=alt.Axis(titleColor=p["bad"], titleAnchor="middle")))
    right_layer = base.mark_line(strokeWidth=2.5, color=p["accent"]).encode(
        x=xenc, y=alt.Y(f"{right}:Q", title=right_title,
                        axis=alt.Axis(format=".0%", titleColor=p["accent"], titleAnchor="middle")))
    selectors = base.mark_point().encode(x=xenc, opacity=alt.value(0)).add_params(nearest, zoom)
    rule = base.mark_rule(color=p["muted"], strokeDash=[4, 3]).encode(
        x=xenc, opacity=alt.condition(nearest, alt.value(0.8), alt.value(0)),
        tooltip=[alt.Tooltip(f"{x}:T", title="Date"), alt.Tooltip(f"{left}:Q", format=",.0f", title=left_title),
                 alt.Tooltip(f"{right}:Q", format=".1%", title=right_title)])
    layered = (alt.layer(left_layer, right_layer, selectors, rule)
               .resolve_scale(y="independent").properties(height=height, title=title or ""))
    event = st.altair_chart(_cfg(layered, p), key=key, on_select="rerun", selection_mode=["zoom"])
    _legend([(left_title, p["bad"]), (right_title, p["accent"])])
    _apply_zoom(event, key, x)


# ---------------------------------------------------------------------------
# Pure builders (page renders these with st.altair_chart)
# ---------------------------------------------------------------------------
def bar(data: pd.DataFrame, cat: str, val: str, *, horizontal: bool = False,
        sort_by_value: bool = True, diverging: bool = False, color: str | None = None,
        height: int = 320, title: str | None = None, fmt: str = "~s",
        cat_title: str | None = None, val_title: str | None = None) -> alt.Chart:
    """Bar chart with angled category labels, value sort, optional diverging colors."""
    p = colors()
    df = data.copy()
    sortspec = alt.EncodingSortField(field=val, order="descending") if sort_by_value else None
    cat_axis = alt.Axis(labelAngle=0 if horizontal else -45, title=cat_title,
                        labelLimit=0, labelOverlap=False)
    val_axis = alt.Axis(format=fmt, titleAnchor="middle")
    cat_channel = alt.Y(f"{cat}:N", sort=sortspec, axis=cat_axis) if horizontal else \
        alt.X(f"{cat}:N", sort=sortspec, axis=cat_axis)
    val_channel = alt.X(f"{val}:Q", title=val_title, axis=val_axis) if horizontal else \
        alt.Y(f"{val}:Q", title=val_title, axis=val_axis)
    if diverging:
        color_enc = alt.condition(f"datum['{val}'] >= 0", alt.value(p["good"]), alt.value(p["bad"]))
        val_fmt = "+,.0f"  # show explicit +/- sign so sign is not color-only
    else:
        color_enc = alt.value(color or p["accent"])
        val_fmt = fmt
    ch = (
        alt.Chart(df).mark_bar(cornerRadiusEnd=2)
        .encode(
            x=val_channel if horizontal else cat_channel,
            y=cat_channel if horizontal else val_channel,
            color=color_enc,
            tooltip=[alt.Tooltip(f"{cat}:N", title=cat_title or cat),
                     alt.Tooltip(f"{val}:Q", format=val_fmt, title=val_title or val)],
        )
        .properties(height=height, title=title or "")
    )
    return _cfg(ch, p, legend_bottom=False)


def scatter(df: pd.DataFrame, x: str, y: str, *, color_field: str, tooltip: list,
            height: int = 380, x_title: str | None = None, y_title: str | None = None,
            x_fmt: str = ".0%", y_fmt: str = ".0%", title: str | None = None,
            label_field: str | None = None, slope1_line: bool = False) -> alt.Chart:
    """Scatter with per-point color, tooltips, optional PM labels, optional slope-1 line.

    ``label_field``: column to show as a text label next to each point.
    ``slope1_line``: if True, draw a dashed return=vol (Sharpe=1) reference line.
    """
    p = colors()
    base = alt.Chart(df)
    points = base.mark_circle(size=150, opacity=0.85, stroke=p["bg"], strokeWidth=1).encode(
        x=alt.X(f"{x}:Q", title=x_title, axis=alt.Axis(format=x_fmt, titleAnchor="middle")),
        y=alt.Y(f"{y}:Q", title=y_title, axis=alt.Axis(format=y_fmt, titleAnchor="middle")),
        color=alt.Color(f"{color_field}:N", scale=alt.Scale(scheme="category20"), legend=None),
        tooltip=tooltip,
    )
    layers = [points]
    if label_field:
        labels = base.mark_text(dx=8, dy=-4, fontSize=10, font=SANS).encode(
            x=alt.X(f"{x}:Q"), y=alt.Y(f"{y}:Q"),
            text=alt.Text(f"{label_field}:N"),
            color=alt.value(p["muted"]),
            tooltip=alt.value(None),  # prevent duplicate tooltip from text layer
        )
        layers.append(labels)
    if slope1_line:
        x_max = float(df[x].max()) * 1.1
        line_df = pd.DataFrame({x: [0, x_max], y: [0, x_max]})
        slope_line = alt.Chart(line_df).mark_line(
            strokeDash=[6, 4], color=p["muted"], opacity=0.5, size=1.5
        ).encode(x=f"{x}:Q", y=f"{y}:Q")
        layers.append(slope_line)
    ch = alt.layer(*layers).properties(height=height, title=title or "")
    return _cfg(ch, p, legend_bottom=False)


def bar_with_return(df: pd.DataFrame, cat: str, pnl_col: str, ret_col: str, *,
                    height: int = 340, title: str | None = None,
                    pnl_title: str = "PnL (USD)", ret_title: str = "Return") -> None:
    """Render bars (PnL, left axis) + return dots (right axis) with a centered two-item legend."""
    p = colors()
    df = df.copy()
    sortspec = alt.EncodingSortField(field=pnl_col, order="descending")
    x_enc = alt.X(f"{cat}:N", sort=sortspec, axis=alt.Axis(labelAngle=-45, title=None,
                                                             labelOverlap=False, labelLimit=0))
    bars = (
        alt.Chart(df).mark_bar(cornerRadiusEnd=3)
        .encode(
            x=x_enc,
            y=alt.Y(f"{pnl_col}:Q", title=pnl_title, axis=alt.Axis(titleAnchor="middle")),
            color=alt.condition(f"datum['{pnl_col}'] >= 0", alt.value(p["good"]), alt.value(p["bad"])),
            tooltip=[alt.Tooltip(f"{cat}:N"), alt.Tooltip(f"{pnl_col}:Q", format=",.0f", title=pnl_title)],
        )
    )
    points = (
        alt.Chart(df).mark_point(size=80, filled=True, color=p["warn"], opacity=0.9)
        .encode(
            x=x_enc,
            y=alt.Y(f"{ret_col}:Q", title=ret_title,
                    axis=alt.Axis(format=".1%", titleColor=p["warn"], titleAnchor="middle")),
            tooltip=[alt.Tooltip(f"{cat}:N"), alt.Tooltip(f"{ret_col}:Q", format=".1%", title=ret_title)],
        )
    )
    ch = alt.layer(bars, points).resolve_scale(y="independent").properties(height=height, title=title or "")
    st.altair_chart(_cfg(ch, p, legend_bottom=False), use_container_width=True)
    _legend([(pnl_title, p["good"]), (ret_title, p["warn"])])


def stacked_cost_bar(df: pd.DataFrame, cat: str, cost_cols: list[str], ratio_col: str, *,
                     height: int = 320, title: str | None = None,
                     ratio_title: str = "Cost / Gross") -> None:
    """Render stacked cost bars + Cost/Gross ratio dot (2nd axis) with a unified centered legend."""
    p = colors()
    # Six perceptually-distinct hues at ~60° spacing on the color wheel.
    # Fixed Tailwind-400 values so they pop equally on dark and light backgrounds.
    _cost_palette = ["#F87171", "#60A5FA", "#FB923C", "#34D399", "#A78BFA", "#FCD34D"]
    cost_colors = _cost_palette[:len(cost_cols)]
    long = df[[cat] + cost_cols].melt(id_vars=cat, var_name="Cost Type", value_name="Cost")
    domain = cost_cols
    # -30° angle: sin(30°)=0.5 vs sin(45°)=0.71 — labels extend ~30% less below the axis,
    # reliably avoiding clipping within the Streamlit chart component.
    _xaxis = alt.Axis(labelAngle=-30, title=None, labelLimit=0, labelOverlap=False)
    stacked = (
        alt.Chart(long).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
        .encode(
            x=alt.X(f"{cat}:N", axis=_xaxis),
            y=alt.Y("Cost:Q", stack="zero", title="Total Cost (USD)", axis=alt.Axis(titleAnchor="middle")),
            color=alt.Color("Cost Type:N",
                            scale=alt.Scale(domain=domain, range=cost_colors),
                            legend=None),
            tooltip=[alt.Tooltip(f"{cat}:N"), alt.Tooltip("Cost Type:N"),
                     alt.Tooltip("Cost:Q", format=",.0f")],
        )
    )
    # Ratio dot: single accent color, filled solid, slightly enlarged for visibility.
    points = (
        alt.Chart(df[df[ratio_col].notna()])
        .mark_point(size=110, filled=True, color=p["accent"], opacity=0.95)
        .encode(
            x=alt.X(f"{cat}:N", axis=_xaxis),
            y=alt.Y(f"{ratio_col}:Q", title=ratio_title,
                    axis=alt.Axis(format=".1%", titleColor=p["accent"], titleAnchor="middle")),
            tooltip=[alt.Tooltip(f"{cat}:N"), alt.Tooltip(f"{ratio_col}:Q", format=".1%", title=ratio_title)],
        )
    )
    ch = (alt.layer(stacked, points).resolve_scale(y="independent")
          .properties(height=height, title=title or ""))
    st.altair_chart(_cfg(ch, p, legend_bottom=False), use_container_width=True)
    # Unified legend: all cost-type color chips + the ratio dot chip.
    _legend([(c, cost_colors[i]) for i, c in enumerate(cost_cols)] + [(ratio_title, p["accent"])])


def html_table(df: pd.DataFrame, *, money_cols: list[str] | None = None,
               pct_cols: list[str] | None = None, na_str: str = "n/a") -> None:
    """Render a compact HTML table with right-aligned numeric columns via --st-* vars.

    Numeric columns are right-aligned so the values line up with the header.
    NaN / None values are displayed as ``na_str``.
    """
    import math
    p = colors()
    money_cols = money_cols or []
    pct_cols = pct_cols or []

    def _fmt(val, col):
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return f'<span style="color:{p["muted"]}">{na_str}</span>'
        if col in money_cols:
            sign = "-" if val < 0 else ""
            color = p["bad"] if val < 0 else ""
            style = f'color:{color};' if color else ""
            a = abs(val)
            txt = f"{sign}${a/1e6:,.1f}M" if a >= 1e6 else f"{sign}${a:,.0f}"
            return f'<span style="{style}">{txt}</span>'
        if col in pct_cols:
            color = p["bad"] if val < 0 else ""
            style = f'color:{color};' if color else ""
            return f'<span style="{style}">{val:.1f}%</span>'
        return str(val)

    header = "".join(
        f'<th style="text-align:right;padding:.3rem .7rem;color:{p["muted"]};font-size:.78rem;'
        f'text-transform:uppercase;letter-spacing:.06em;font-weight:600;'
        f'border-bottom:1px solid {p["border"]};">{c}</th>'
        for c in df.columns
    )
    rows_html = ""
    for _, row in df.iterrows():
        cells = "".join(
            f'<td style="text-align:right;padding:.28rem .7rem;font-family:IBM Plex Mono,monospace;'
            f'font-variant-numeric:tabular-nums;font-size:.88rem;">{_fmt(row[c], c)}</td>'
            for c in df.columns
        )
        rows_html += f"<tr>{cells}</tr>"
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;background:{p["surface"]};'
        f'border:1px solid {p["border"]};border-radius:10px;overflow:hidden;">'
        f"<thead><tr>{header}</tr></thead><tbody>{rows_html}</tbody></table>",
        unsafe_allow_html=True,
    )


def show_sweep(
    df: pd.DataFrame, x: str, current_x: float, *,
    selected_x: float | None = None,
    height: int = 320, title: str | None = None, x_title: str = "Payout Ratio",
) -> None:
    """Render a sensitivity sweep with centered legend and optional slider marker.

    Args:
        current_x:  the fund's actual (baseline) payout ratio — dashed amber line.
        selected_x: the slider-selected value — solid accent vertical line.
                    Appears only when different from current_x.
    """
    p = colors()
    series_names = [c for c in df.columns]
    palette = [p["bad"], p["accent"]]
    long = df.reset_index().melt(x, var_name="Series", value_name="value")
    ymax = float(long["value"].max())
    ymin = float(long["value"].min())

    base = alt.Chart(long).mark_line(strokeWidth=2.5).encode(
        x=alt.X(f"{x}:Q", axis=alt.Axis(format=".0%", title=x_title)),
        y=alt.Y("value:Q", title="USD", axis=alt.Axis(titleAnchor="middle")),
        color=alt.Color("Series:N", scale=alt.Scale(domain=series_names, range=palette), legend=None),
        tooltip=[alt.Tooltip(f"{x}:Q", format=".0%", title=x_title), alt.Tooltip("Series:N"),
                 alt.Tooltip("value:Q", format=",.0f")],
    )

    # Baseline: dashed amber = fund's current ratio.
    cur_df = pd.DataFrame({x: [current_x], "value": [ymax]})
    cur_rule  = alt.Chart(cur_df).mark_rule(color=p["warn"], strokeDash=[5, 4], size=2).encode(x=f"{x}:Q")
    cur_label = alt.Chart(cur_df).mark_text(
        text=f"current {current_x:.0%}", color=p["warn"], align="left", dx=6, baseline="top",
        fontWeight=600, font=SANS,
    ).encode(x=f"{x}:Q", y="value:Q")

    layers = [base, cur_rule, cur_label]

    # Slider line: solid accent = selected ratio (only when different from baseline).
    if selected_x is not None and abs(selected_x - current_x) > 1e-6:
        sel_df = pd.DataFrame({x: [selected_x], "value": [ymin]})
        sel_rule = alt.Chart(sel_df).mark_rule(color=p["accent2"], size=2.5).encode(x=f"{x}:Q")
        sel_label = alt.Chart(sel_df).mark_text(
            text=f"selected {selected_x:.0%}", color=p["accent2"], align="left", dx=6, baseline="bottom",
            fontWeight=600, font=SANS,
        ).encode(x=f"{x}:Q", y="value:Q")
        layers.extend([sel_rule, sel_label])

    ch = _cfg(alt.layer(*layers).properties(height=height, title=title or ""), p)
    st.altair_chart(ch, use_container_width=True)
    _legend([(s, palette[i]) for i, s in enumerate(series_names)])


def waterfall(steps: list[tuple], *, height: int = 360, title: str | None = None,
              fmt: str = "~s") -> alt.Chart:
    """Bridge waterfall. ``steps`` = list of ``(label, value, kind)`` with kind in
    ``{'total','delta'}``; totals are drawn from zero, deltas float on the running sum.
    """
    p = colors()
    rows, running = [], 0.0
    for label, value, kind in steps:
        if kind == "total":
            start, end, running = 0.0, float(value), float(value)
            direction = "total"
        else:
            start = running
            running += float(value)
            end = running
            direction = "up" if value >= 0 else "down"
        rows.append({"label": label, "lo": min(start, end), "hi": max(start, end),
                     "amount": float(value), "dir": direction})
    df = pd.DataFrame(rows)
    order = [r["label"] for r in rows]
    scale = alt.Scale(domain=["total", "up", "down"], range=[p["accent2"], p["good"], p["bad"]])
    ch = (
        alt.Chart(df).mark_bar(size=30, cornerRadius=2)
        .encode(
            x=alt.X("label:N", sort=order,
                    axis=alt.Axis(labelAngle=-30, title=None, labelLimit=0, labelOverlap=False)),
            y=alt.Y("lo:Q", title="USD", axis=alt.Axis(format=fmt, titleAnchor="middle")),
            y2="hi:Q",
            color=alt.Color("dir:N", scale=scale, legend=None),
            tooltip=[alt.Tooltip("label:N", title="Component"),
                     alt.Tooltip("amount:Q", format=",.0f", title="Amount")],
        )
        .properties(height=height, title=title or "")
    )
    return _cfg(ch, p, legend_bottom=False)
