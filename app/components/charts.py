"""Theme-aware Altair chart builders shared by every page.

Altair (Vega-Lite, bundled with Streamlit, pure-Python) replaces the bare
``st.*_chart`` calls so we can control what those cannot: angled axis labels,
zoom/pan, legend placement, tooltips, sorting, diverging colors, waterfalls, and
dual-axis overlays. Every builder reads the active palette from ``theme`` so
charts restyle instantly when the user switches theme.
"""
from __future__ import annotations

import altair as alt
import pandas as pd

from app.components.theme import active_palette

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


def line(df: pd.DataFrame, *, x: str = "date", height: int = 320, zoom: bool = True,
         title: str | None = None, y_title: str = "USD", date_fmt: str = "%b %Y") -> alt.Chart:
    """Multi-series line chart (wide df). Zoom/pan enabled; legend at the bottom."""
    p = active_palette()
    data = df.reset_index() if x not in df.columns else df.copy()
    series = [c for c in data.columns if c != x]
    long = data.melt(id_vars=[x], value_vars=series, var_name="Series", value_name="value")
    ch = (
        alt.Chart(long).mark_line(strokeWidth=2)
        .encode(
            x=alt.X(f"{x}:T", title=None, axis=alt.Axis(format=date_fmt)),
            y=alt.Y("value:Q", title=y_title, axis=alt.Axis(titleAnchor="middle")),
            color=alt.Color("Series:N", scale=alt.Scale(range=p["scheme"]),
                            legend=alt.Legend(title=None)),
            tooltip=[alt.Tooltip(f"{x}:T", title="Date"), alt.Tooltip("Series:N"),
                     alt.Tooltip("value:Q", format=",.0f", title="Value")],
        )
        .properties(height=height, title=title or "")
    )
    if zoom:
        ch = ch.interactive()
    return _cfg(ch, p)


def bar(data: pd.DataFrame, cat: str, val: str, *, horizontal: bool = False,
        sort_by_value: bool = True, diverging: bool = False, color: str | None = None,
        height: int = 320, title: str | None = None, fmt: str = "~s",
        cat_title: str | None = None, val_title: str | None = None) -> alt.Chart:
    """Bar chart with angled category labels, value sort, optional diverging colors."""
    p = active_palette()
    df = data.copy()
    sortspec = alt.EncodingSortField(field=val, order="descending") if sort_by_value else None
    cat_axis = alt.Axis(labelAngle=0 if horizontal else -45, title=cat_title)
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
            x_fmt: str = ".0%", y_fmt: str = ".0%", title: str | None = None) -> alt.Chart:
    """Scatter with one color per category, tooltips, and a bottom legend."""
    p = active_palette()
    ch = (
        alt.Chart(df).mark_circle(size=150, opacity=0.85, stroke=p["bg"], strokeWidth=1)
        .encode(
            x=alt.X(f"{x}:Q", title=x_title, axis=alt.Axis(format=x_fmt, titleAnchor="middle")),
            y=alt.Y(f"{y}:Q", title=y_title, axis=alt.Axis(format=y_fmt, titleAnchor="middle")),
            color=alt.Color(f"{color_field}:N", scale=alt.Scale(range=p["scheme"]),
                            legend=alt.Legend(title=None, columns=6)),
            tooltip=tooltip,
        )
        .properties(height=height, title=title or "")
    )
    return _cfg(ch, p)


def area(df: pd.DataFrame, val: str, *, x: str = "date", height: int = 300,
         color: str | None = None, y_title: str = "USD", title: str | None = None) -> alt.Chart:
    """Single-series filled area (e.g. accrued liability)."""
    p = active_palette()
    data = df.reset_index() if x not in df.columns else df.copy()
    c = color or p["bad"]
    ch = (
        alt.Chart(data).mark_area(opacity=0.75, line={"color": c}, color=c)
        .encode(
            x=alt.X(f"{x}:T", title=None, axis=alt.Axis(format="%b %Y")),
            y=alt.Y(f"{val}:Q", title=y_title, axis=alt.Axis(titleAnchor="middle")),
            tooltip=[alt.Tooltip(f"{x}:T", title="Date"), alt.Tooltip(f"{val}:Q", format=",.0f")],
        )
        .properties(height=height, title=title or "")
    )
    return _cfg(ch, p)


def dual_line(df: pd.DataFrame, left: str, right: str, *, x: str = "date",
              left_title: str = "USD", right_title: str = "%", height: int = 320,
              title: str | None = None) -> alt.Chart:
    """Area (left axis, $) + line (right axis, %) on independent scales."""
    p = active_palette()
    data = df.reset_index() if x not in df.columns else df.copy()
    base = alt.Chart(data).encode(x=alt.X(f"{x}:T", title=None, axis=alt.Axis(format="%b %Y")))
    left_layer = base.mark_area(opacity=0.65, color=p["bad"], line={"color": p["bad"]}).encode(
        y=alt.Y(f"{left}:Q", title=left_title, axis=alt.Axis(titleColor=p["bad"], titleAnchor="middle")),
        tooltip=[alt.Tooltip(f"{left}:Q", format=",.0f", title=left_title)],
    )
    right_layer = base.mark_line(strokeWidth=2.5, color=p["accent"]).encode(
        y=alt.Y(f"{right}:Q", title=right_title,
                axis=alt.Axis(format=".0%", titleColor=p["accent"], titleAnchor="middle")),
        tooltip=[alt.Tooltip(f"{right}:Q", format=".1%", title=right_title)],
    )
    ch = alt.layer(left_layer, right_layer).resolve_scale(y="independent").properties(
        height=height, title=title or ""
    )
    return _cfg(ch, p)


def sweep_curve(df: pd.DataFrame, x: str, current_x: float, *, height: int = 320,
                title: str | None = None, x_title: str = "Payout Ratio") -> alt.Chart:
    """Sensitivity sweep (wide df indexed by ``x``) with a marked 'current' value."""
    p = active_palette()
    long = df.reset_index().melt(x, var_name="Series", value_name="value")
    ymax = float(long["value"].max())
    base = alt.Chart(long).mark_line(strokeWidth=2.5).encode(
        x=alt.X(f"{x}:Q", axis=alt.Axis(format=".0%", title=x_title)),
        y=alt.Y("value:Q", title="USD", axis=alt.Axis(titleAnchor="middle")),
        color=alt.Color("Series:N", scale=alt.Scale(range=[p["bad"], p["accent"]]),
                        legend=alt.Legend(title=None)),
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
    p = active_palette()
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
