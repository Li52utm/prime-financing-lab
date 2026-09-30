from dataclasses import replace

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import assumptions as A
from engine.financing import breakeven_trs_spread, pb_route, trs_route, upgrade_route
from ui.common import (
    INK_2, MUTED, OTHER_COLORS, ROUTE_COLORS, ROUTES, bp, explain, gbp, over_sonia_bp,
    page_header, pct, show, style, table,
)
from ui.ticket import get_ctx

ctx = get_ctx()
x = ctx.fin
page_header("Client view", ctx)
fins = {r.route: r for r in (pb_route(x), trs_route(x), upgrade_route(x))}

# --- Headline: financing cost, bp over SONIA --------------------------------------
cols = st.columns(3)
for col, route in zip(cols, ROUTES):
    f = fins[route]
    with col.container(border=True):
        st.markdown(f"**{route}**")
        st.metric("Financing, bp over SONIA", f"{over_sonia_bp(f.financing_cost, x):,.1f} bp",
                  f"all-in {pct(f.financing_cost / (x.notional * x.tenor_days / 365))}",
                  delta_color="off")
        st.metric("Net of dividends, bp over SONIA", f"{over_sonia_bp(f.net_cost, x):,.1f} bp",
                  delta_color="off")
        parts = "\n".join(f"- {k.replace('_', ' ')}: {gbp(v)}" for k, v in f.client_parts.items()
                          if v)
        explain(f"{route} client cost", f"""
Financing cost over {x.tenor_days} days = sum of the parts below except the dividend credit
= **{gbp(f.financing_cost)}**. Net = financing − dividend credit = **{gbp(f.net_cost)}**.

{parts}

bp over SONIA = cost / (N × τ) − SONIA, with N = {gbp(x.notional)}, τ = {x.tenor_days}/365,
SONIA {pct(x.sonia)} (placeholder). Margin funding uses the client's own rate
{pct(x.client_funding_rate)} (own assumption).
""")

# --- Table with and without SDRT ------------------------------------------------------
st.subheader("Cost table")
rows = []
for route in ROUTES:
    f = fins[route]
    rows.append({
        "Route": route,
        "Financing bp/SONIA": over_sonia_bp(f.financing_cost, x),
        "Financing ex SDRT bp/SONIA": over_sonia_bp(f.financing_cost_ex_sdrt, x),
        "Dividend credit (bp)": f.dividend_credit / (x.notional * x.tenor_days / 365) * 1e4,
        "Net bp/SONIA": over_sonia_bp(f.net_cost, x),
        "All-in financing (%)": f.financing_cost / (x.notional * x.tenor_days / 365) * 100,
        "Financing (GBP)": f.financing_cost,
        "SDRT one-off (GBP)": f.sdrt_one_off,
        "SDRT this tenor (GBP)": f.sdrt,
    })
table(pd.DataFrame(rows), {
    "Financing bp/SONIA": "bp", "Financing ex SDRT bp/SONIA": "bp", "Dividend credit (bp)": "bp",
    "Net bp/SONIA": "bp", "All-in financing (%)": "pct", "Financing (GBP)": "gbp",
    "SDRT one-off (GBP)": "gbp", "SDRT this tenor (GBP)": "gbp"})
st.caption(f"SDRT {'on' if x.include_sdrt else 'off'}; one-off 0.5% on purchase, amortised over "
           f"{x.holding_period_days} days; AIM shares exempt; the TRS client pays none. "
           "Price moves and variation margin are ignored (static notional).")

# --- Waterfall per route ---------------------------------------------------------------
st.subheader("Where the cost comes from")
route = st.radio("Route", ROUTES, horizontal=True, key="client_waterfall_route")
f = fins[route]
labels, values = [], []
for k, v in f.client_parts.items():
    if v:
        labels.append(k.replace("_", " ").capitalize())
        values.append(v)
fig = go.Figure(go.Waterfall(
    x=[*labels, "Net cost"], y=[*values, 0], measure=["relative"] * len(values) + ["total"],
    increasing={"marker": {"color": ROUTE_COLORS[route]}},
    decreasing={"marker": {"color": OTHER_COLORS[2]}},
    totals={"marker": {"color": MUTED}},
    connector={"line": {"color": "#383835", "width": 1}},
    hovertemplate="%{x}: £%{y:,.0f}<extra></extra>",
))
show(style(fig, f"{route}: client cost over {x.tenor_days} days (GBP)", y_title="GBP"))
explain("waterfall", "Bars add up from the first component to the net cost. Credits "
        "(dividend, IM remuneration) step down. Values in GBP over the tenor.")

# --- Breakeven TRS spread ------------------------------------------------------------
st.subheader("TRS spread breakeven against PB and the upgrade")
be = breakeven_trs_spread(x)
hi = max(A.BREAKEVEN_CHART_MAX_SPREAD, be * 1.2 if be > 0 else 0)
grid = [hi * i / 30 for i in range(31)]
trs_net = [over_sonia_bp(trs_route(replace(x, trs_spread=s)).net_cost, x) for s in grid]
fig = go.Figure()
fig.add_scatter(x=[s * 1e4 for s in grid], y=trs_net, name="TRS net", mode="lines",
                line={"color": ROUTE_COLORS["TRS"], "width": 2},
                hovertemplate="TRS spread %{x:.0f} bp<br>net %{y:.1f} bp over SONIA<extra></extra>")
for rt in ("PB", "Collateral upgrade"):
    fig.add_scatter(x=[0, hi * 1e4], y=[over_sonia_bp(fins[rt].net_cost, x)] * 2,
                    name=f"{rt} net", mode="lines",
                    line={"color": ROUTE_COLORS[rt], "width": 2, "dash": "dot"},
                    hovertemplate="%{y:.1f} bp over SONIA<extra>" + rt + "</extra>")
fig.add_scatter(x=[be * 1e4], y=[over_sonia_bp(fins["PB"].net_cost, x)], mode="markers+text",
                name="Breakeven vs PB", marker={"size": 10, "color": INK_2},
                text=[f"  {be * 1e4:.0f} bp"], textposition="middle right",
                hovertemplate="breakeven %{x:.1f} bp<extra></extra>")
fig.add_vline(x=x.trs_spread * 1e4, line={"color": MUTED, "dash": "dash", "width": 1},
              annotation_text="quoted", annotation_position="top")
show(style(fig, "Client net cost against TRS spread", x_title="TRS spread (bp over SONIA)",
           y_title="Net cost (bp over SONIA)"))
explain("breakeven TRS spread", f"""
TRS net cost rises one-for-one with the TRS spread. The breakeven is where it crosses the PB
net cost: **{bp(be)}** (quoted {bp(x.trs_spread)}).
""")
