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


def show_line(df: pd.DataFrame, *, key: str, x: str = "date", y_title: str = "USD",
              height: int = 320, title: str | None = None) -> None:
    """Render a multi-series line chart with drag-zoom, hover guide, centered legend."""
    p = colors()
    data = df.reset_index() if x not in df.columns else df.copy()
    data = _zoom_filter(data, x, key)
    series = [c for c in data.columns if c != x]
    long = data.melt(id_vars=[x], value_vars=series, var_name="Series", value_name="value")
    xenc = _xenc(x)
    nearest, zoom = _hover_zoom_params(x)
    color = alt.Color("Series:N", scale=alt.Scale(range=p["scheme"]), legend=None)
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
    _legend([(s, p["scheme"][i % len(p["scheme"])]) for i, s in enumerate(series)])
    _apply_zoom(event, key, x)


def show_area(df: pd.DataFrame, val: str, *, key: str, x: str = "date", height: int = 280,
              color: str | None = None, y_title: str = "USD", title: str | None = None) -> None:
    """Render a single-series area with drag-zoom and a hover guide line."""
    p = colors()
    c = color or p["bad"]
    data = df.reset_index() if x not in df.columns else df.copy()
    data = _zoom_filter(data, x, key)
    xenc = _xenc(x)
    nearest, zoom = _hover_zoom_params(x)
    base = alt.Chart(data)
    area = base.mark_area(opacity=0.75, line={"color": c}, color=c).encode(
        x=xenc, y=alt.Y(f"{val}:Q", title=y_title, axis=alt.Axis(titleAnchor="middle")),
        tooltip=[alt.Tooltip(f"{x}:T", title="Date"), alt.Tooltip(f"{val}:Q", format=",.0f")])
    selectors = base.mark_point().encode(x=xenc, opacity=alt.value(0)).add_params(nearest, zoom)
    rule = base.mark_rule(color=p["muted"], strokeDash=[4, 3]).encode(
        x=xenc, opacity=alt.condition(nearest, alt.value(0.8), alt.value(0)))
    chart = _cfg(alt.layer(area, selectors, rule).properties(height=height, title=title or ""), p)
    event = st.altair_chart(chart, key=key, on_select="rerun", selection_mode=["zoom"])
    _apply_zoom(event, key, x)


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
    else:
        color_enc = alt.value(color or p["accent"])
    ch = (
        alt.Chart(df).mark_bar(cornerRadiusEnd=2)
        .encode(
            x=val_channel if horizontal else cat_channel,
            y=cat_channel if horizontal else val_channel,
            color=color_enc,
            tooltip=[alt.Tooltip(f"{cat}:N", title=cat_title or cat),
                     alt.Tooltip(f"{val}:Q", format=",.0f", title=val_title or val)],
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
        color=alt.Color(f"{color_field}:N", scale=alt.Scale(range=p["scheme"]), legend=None),
        tooltip=tooltip,
    )
    layers = [points]
    if label_field:
        labels = base.mark_text(dx=8, dy=-4, fontSize=10, font=SANS).encode(
            x=alt.X(f"{x}:Q"), y=alt.Y(f"{y}:Q"),
            text=alt.Text(f"{label_field}:N"),
            color=alt.value(p["muted"]),
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
                    pnl_title: str = "PnL (USD)", ret_title: str = "Return") -> alt.Chart:
    """Bars (PnL, left axis) + points (return, right axis) — dual-axis combo.

    Shows PnL magnitude and return-on-capital side by side without a toggle.
    """
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
    return _cfg(ch, p, legend_bottom=False)


def stacked_cost_bar(df: pd.DataFrame, cat: str, cost_cols: list[str], ratio_col: str, *,
                     height: int = 320, title: str | None = None,
                     ratio_title: str = "Cost / Gross") -> alt.Chart:
    """Stacked bars (financing/borrow/commission/fx/center) + Cost/Gross point on 2nd axis."""
    p = colors()
    cost_colors = [p["accent2"], p["bad"], p["warn"], p["accent"], p["muted"]][:len(cost_cols)]
    long = df[[cat] + cost_cols].melt(id_vars=cat, var_name="Cost Type", value_name="Cost")
    domain = cost_cols
    stacked = (
        alt.Chart(long).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
        .encode(
            x=alt.X(f"{cat}:N", axis=alt.Axis(labelAngle=-45, title=None, labelOverlap=False, labelLimit=0)),
            y=alt.Y("Cost:Q", stack="zero", title="Total Cost (USD)", axis=alt.Axis(titleAnchor="middle")),
            color=alt.Color("Cost Type:N",
                            scale=alt.Scale(domain=domain, range=cost_colors),
                            legend=alt.Legend(title=None, orient="bottom")),
            tooltip=[alt.Tooltip(f"{cat}:N"), alt.Tooltip("Cost Type:N"),
                     alt.Tooltip("Cost:Q", format=",.0f")],
        )
    )
    points = (
        alt.Chart(df[df[ratio_col].notna()]).mark_point(size=80, filled=True, color=p["warn"], opacity=0.9)
        .encode(
            x=alt.X(f"{cat}:N", axis=alt.Axis(labelAngle=-45, title=None, labelOverlap=False, labelLimit=0)),
            y=alt.Y(f"{ratio_col}:Q", title=ratio_title,
                    axis=alt.Axis(format=".1%", titleColor=p["warn"], titleAnchor="middle")),
            tooltip=[alt.Tooltip(f"{cat}:N"), alt.Tooltip(f"{ratio_col}:Q", format=".1%", title=ratio_title)],
        )
    )
    ch = alt.layer(stacked, points).resolve_scale(y="independent").properties(height=height, title=title or "")
    return _cfg(ch, p)


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


def sweep_curve(df: pd.DataFrame, x: str, current_x: float, *, height: int = 320,
                title: str | None = None, x_title: str = "Payout Ratio") -> alt.Chart:
    """Sensitivity sweep (wide df indexed by ``x``) with a marked 'current' value."""
    p = colors()
    long = df.reset_index().melt(x, var_name="Series", value_name="value")
    ymax = float(long["value"].max())
    base = alt.Chart(long).mark_line(strokeWidth=2.5).encode(
        x=alt.X(f"{x}:Q", axis=alt.Axis(format=".0%", title=x_title)),
        y=alt.Y("value:Q", title="USD", axis=alt.Axis(titleAnchor="middle")),
        color=alt.Color("Series:N", scale=alt.Scale(range=[p["bad"], p["accent"]]),
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip(f"{x}:Q", format=".0%", title=x_title), alt.Tooltip("Series:N"),
                 alt.Tooltip("value:Q", format=",.0f")],
    )
    mark_df = pd.DataFrame({x: [current_x], "value": [ymax]})
    rule = alt.Chart(mark_df).mark_rule(color=p["warn"], strokeDash=[5, 4], size=2).encode(x=f"{x}:Q")
    label = alt.Chart(mark_df).mark_text(
        text=f"current {current_x:.0%}", color=p["warn"], align="left", dx=6, baseline="top",
        fontWeight=600, font=SANS).encode(x=f"{x}:Q", y="value:Q")
    ch = alt.layer(base, rule, label).properties(height=height, title=title or "")
    return _cfg(ch, p)


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
            x=alt.X("label:N", sort=order, axis=alt.Axis(labelAngle=-45, title=None)),
            y=alt.Y("lo:Q", title="USD", axis=alt.Axis(format=fmt, titleAnchor="middle")),
            y2="hi:Q",
            color=alt.Color("dir:N", scale=scale, legend=None),
            tooltip=[alt.Tooltip("label:N", title="Component"),
                     alt.Tooltip("amount:Q", format=",.0f", title="Amount")],
        )
        .properties(height=height, title=title or "")
    )
    return _cfg(ch, p, legend_bottom=False)
