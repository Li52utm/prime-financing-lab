import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import assumptions as A
from engine.capital import best_for_desk, capital_comparison, k_sensitivity, role_grid
from engine.financing import breakeven_trs_spread, pb_route, trs_route, upgrade_route
from ui.common import (
    DIVERGING, INK, MUTED, ROUTE_COLORS, ROUTE_DASHES, ROUTES, SURFACE, bp,
    clearance_sentence, explain, gbp, over_sonia_bp, page_header, pct, route_line, show, style,
    table, tag,
)
from ui.ticket import get_ctx

ctx = get_ctx()
x, c = ctx.fin, ctx.cap
page_header("Summary", ctx)

cap = capital_comparison(x, c).set_index("route")
fins = {r.route: r for r in (pb_route(x), trs_route(x), upgrade_route(x))}
k = x.shadow_cost_k
tau_txt = f"{x.tenor_days}/365"

# --- Verdict ---------------------------------------------------------------------
best = best_for_desk(cap.reset_index())
if best is None:
    st.info(f"No route clears the balance-sheet charge k = {pct(k)} at quoted spreads. "
            "No best-for-desk route is named.")
else:
    st.success(f"Clears k = {pct(k)}: {best} has the highest return on leverage exposure "
               "among routes that clear.")

# --- Lead: break-even k and required vs quoted spread, per route -------------------
st.subheader("Break-even balance-sheet charge and required spread")
cols = st.columns(3)
for col, route in zip(cols, ROUTES):
    row = cap.loc[route]
    lever = "fee" if route == "Collateral upgrade" else "spread"
    with col.container(border=True):
        st.markdown(f"**{route}**")
        be = row["break_even_k"]
        st.metric("Break-even k", bp(be), f"{(be - k) * 1e4:+.1f} bp vs k", delta_color="off")
        st.metric(f"Required {lever} for RoLE = k", bp(row["required_spread_role"]),
                  f"quoted {bp(row['current_spread'])}", delta_color="off")
        clears = bool(row["clears_role_hurdle"])
        st.markdown(tag(clears)
                    + f" · cushion {row['role_hurdle_cushion_bp']:+.1f} bp of {lever}")
        base = x.notional * (1 - x.pb_margin) if route == "PB" else x.notional
        explain(f"{route} break-even k and required {lever}", f"""
**Break-even k** is the balance-sheet charge at which the route just clears. It equals the
gross return on leverage exposure (RoLE):

RoLE = dealer net / (leverage exposure × τ) = {gbp(row['dealer_net_gbp'])} /
({gbp(row['leverage_exposure_gbp'])} × {tau_txt}) = **{bp(be)}**

**Required {lever}**: dealer net is linear in the {lever}, net(s) = a + B·s·τ with
B = {gbp(base)} and a = net − B·s_quoted·τ. Solve a + B·s·τ = k × leverage × τ:
s = (k·LE·τ − a) / (B·τ) = **{bp(row['required_spread_role'])}** against quoted
{bp(row['current_spread'])}.

**Clears** if RoLE ≥ k. Cushion = quoted − required = {row['role_hurdle_cushion_bp']:+.1f} bp.
Leverage exposure is illustrative (PRA Leverage Ratio (CRR) Art 429b/429c/429e); see Capital.
""")

# --- One table, three routes -------------------------------------------------------
st.subheader("All routes")
rows = []
for route in ROUTES:
    r, f = cap.loc[route], fins[route]
    rows.append({
        "Route": route,
        "Break-even k (bp)": r["break_even_k"] * 1e4,
        "k (bp)": k * 1e4,
        "Clears k": "Yes" if r["clears_role_hurdle"] else "No",
        "Quoted (bp)": r["current_spread"] * 1e4,
        "Req. RoLE (bp)": r["required_spread_role"] * 1e4,
        "Req. RoRWA (bp)": r["required_spread_rorwa"] * 1e4,
        "Binding": r["binding"],
        "Cushion (bp)": r["role_hurdle_cushion_bp"],
        "Client fin. bp/SONIA": over_sonia_bp(f.financing_cost, x),
        "Client net bp/SONIA": over_sonia_bp(f.net_cost, x),
        "Dealer net (GBP)": r["dealer_net_gbp"],
        "Leverage (GBP m)": r["leverage_exposure_gbp"] / 1e6,
        "RWA (GBP m)": r["rwa_gbp"] / 1e6,
        "RoRWA (%)": r["rorwa"] * 100,
    })
table(pd.DataFrame(rows), {
    "Break-even k (bp)": "bp", "k (bp)": "bp", "Quoted (bp)": "bp", "Req. RoLE (bp)": "bp",
    "Req. RoRWA (bp)": "bp", "Cushion (bp)": "bp", "Client fin. bp/SONIA": "bp",
    "Client net bp/SONIA": "bp", "Dealer net (GBP)": "gbp", "Leverage (GBP m)": "m",
    "RWA (GBP m)": "m", "RoRWA (%)": "pct"})
st.caption("Quoted spread for the upgrade is the upgrade fee. Client costs are annualised per "
           "GBP of notional, shown as bp over SONIA. Binding = the higher required spread of the "
           f"RoLE (k) and RoRWA ({pct(c.target_rorwa)}) targets.")

# --- Client and TRS headlines ------------------------------------------------------
c1, c2 = st.columns(2)
with c1.container(border=True):
    net_bp = {rt: over_sonia_bp(fins[rt].net_cost, x) for rt in ROUTES}
    cheapest = min(net_bp, key=net_bp.get)
    st.metric("Cheapest for client (net of dividends)", cheapest,
              f"{net_bp[cheapest]:+.1f} bp over SONIA", delta_color="off")
    explain("cheapest for client", f"""
Client net cost = financing cost − dividend credit, annualised per GBP of notional:
net / (N × τ) − SONIA. PB {net_bp['PB']:+.1f} bp, TRS {net_bp['TRS']:+.1f} bp, upgrade
{net_bp['Collateral upgrade']:+.1f} bp over SONIA. Financing includes the client's own
funding of its margin at {pct(x.client_funding_rate)} and SDRT amortised over
{x.holding_period_days} days. See Client view for the breakdown.
""")
with c2.container(border=True):
    be_trs = breakeven_trs_spread(x)
    st.metric("Breakeven TRS spread (client indifferent to PB)", bp(be_trs),
              f"quoted {bp(x.trs_spread)}", delta_color="off")
    explain("breakeven TRS spread", f"""
The TRS spread s at which the client's TRS net cost equals its PB net cost:
N(SONIA + s)τ + N·IM·r_c·τ − IM remuneration − pass-through × dividend = PB net cost.
Solved in closed form: **{bp(be_trs)}**. SDRT is {'on' if x.include_sdrt else 'off'} and
amortised over {x.holding_period_days} days.
""")

# --- k sensitivity -----------------------------------------------------------------
st.subheader("Sensitivity to the balance-sheet charge k")
ks = k_sensitivity(x, c)
fig = go.Figure()
for route in ROUTES:
    d = ks[ks["route"] == route]
    fig.add_scatter(x=d["k"] * 100, y=d["required_spread_role"] * 1e4, name=f"{route} required",
                    mode="lines+markers", **route_line(route),
                    hovertemplate="k %{x:.2f}%<br>required %{y:.1f} bp<extra>" + route + "</extra>")
    fig.add_scatter(x=[ks["k"].min() * 100, ks["k"].max() * 100],
                    y=[cap.loc[route, "current_spread"] * 1e4] * 2, name=f"{route} quoted",
                    mode="lines", opacity=0.85,
                    line={"color": ROUTE_COLORS[route], "width": 1, "dash": ROUTE_DASHES[route]},
                    hovertemplate="quoted %{y:.1f} bp<extra>" + route + "</extra>")
fig.add_vline(x=k * 100, line={"color": MUTED, "width": 1, "dash": "dash"},
              annotation_text=f"k = {pct(k)}", annotation_position="top")
show(style(fig, "Required spread for RoLE = k vs quoted (thin line)",
           x_title="Balance-sheet charge k (%)", y_title="Spread / fee (bp)"))
explain("k sensitivity", """
For each k from 0 to 3%, the required spread is the one at which gross RoLE equals k (formula
above). Gross RoLE does not depend on k, so a route clears wherever its dotted quoted line sits
above its solid required line, i.e. for k up to its break-even k.
""")
wide = ks.pivot(index="k", columns="route", values="required_spread_role").mul(1e4)
wide.insert(0, "k (%)", wide.index * 100)
table(wide[["k (%)", *ROUTES]].rename(columns={r: f"{r} req. (bp)" for r in ROUTES}),
      {"k (%)": "pct", **{f"{r} req. (bp)": "bp" for r in ROUTES}})

# --- Spread vs k heatmaps -------------------------------------------------------------
st.subheader("Spread vs k: where each route clears")
with st.expander("Axis ranges"):
    a1, a2, a3, a4 = st.columns(4)
    s_min = a1.number_input("Spread from (bp)", 0.0, 1000.0, A.HEATMAP_SPREAD_MIN_BP, 5.0,
                            key="hm_s_min")
    s_max = a2.number_input("Spread to (bp)", 5.0, 1000.0, A.HEATMAP_SPREAD_MAX_BP, 5.0,
                            key="hm_s_max")
    k_min = a3.number_input("k from (bp)", 0.0, 1000.0, A.HEATMAP_K_MIN_BP, 5.0, key="hm_k_min")
    k_max = a4.number_input("k to (bp)", 5.0, 1000.0, A.HEATMAP_K_MAX_BP, 5.0, key="hm_k_max")
if s_max <= s_min or k_max <= k_min:
    st.warning("Each axis needs 'to' above 'from'; showing the defaults.")
    s_min, s_max = A.HEATMAP_SPREAD_MIN_BP, A.HEATMAP_SPREAD_MAX_BP
    k_min, k_max = A.HEATMAP_K_MIN_BP, A.HEATMAP_K_MAX_BP


def axis(lo: float, hi: float) -> np.ndarray:
    """At most ~60 cells per axis; at least the default step."""
    step = max(A.HEATMAP_STEP_BP, (hi - lo) / 60)
    return np.arange(lo, hi + step / 2, step)


spreads_bp, ks_bp = axis(s_min, s_max), axis(k_min, k_max)
grids = {}
for route in ROUTES:
    g = role_grid(x, c, route, list(spreads_bp / 1e4), list(ks_bp / 1e4))
    grids[route] = g.pivot(index="k", columns="spread", values="role_minus_k").to_numpy() * 1e4
finite = np.concatenate([v[np.isfinite(v)] for v in grids.values()] or [np.array([1.0])])
zmax = float(np.nanmax(np.abs(finite))) if finite.size else 1.0  # one shared, symmetric scale

fig = make_subplots(rows=1, cols=3, shared_yaxes=True, horizontal_spacing=0.04,
                    subplot_titles=[f"{r} ({'fee' if r == 'Collateral upgrade' else 'spread'})"
                                    for r in ROUTES])
for i, route in enumerate(ROUTES, start=1):
    z = grids[route]
    role_bp = z + ks_bp[:, None]
    custom = np.dstack([role_bp.astype(object),
                        np.where(z >= 0, "clears", "misses").astype(object)])
    fig.add_trace(go.Heatmap(
        x=spreads_bp, y=ks_bp, z=z, coloraxis="coloraxis", customdata=custom,
        hovertemplate=("spread %{x:.0f} bp<br>k %{y:.0f} bp<br>RoLE %{customdata[0]:.1f} bp"
                       "<br>RoLE − k %{z:.1f} bp<br>%{customdata[1]}<extra>" + route
                       + "</extra>")), row=1, col=i)
    if np.isfinite(z).any() and np.nanmin(z) < 0 < np.nanmax(z):
        fig.add_trace(go.Contour(
            x=spreads_bp, y=ks_bp, z=z, showscale=False, hoverinfo="skip",
            contours={"start": 0, "end": 0, "size": 1, "coloring": "lines"},
            line={"width": 3, "color": INK}, colorscale=[[0, INK], [1, INK]]), row=1, col=i)
    row = cap.loc[route]
    fig.add_trace(go.Scatter(
        x=[row["current_spread"] * 1e4], y=[k * 1e4], mode="markers", showlegend=False,
        marker={"size": 13, "symbol": "circle", "color": INK,
                "line": {"color": SURFACE, "width": 2}},
        hovertemplate=(f"current: {row['current_spread'] * 1e4:.1f} bp, k {k * 1e4:.0f} bp"
                       "<extra>" + route + "</extra>")), row=1, col=i)
style(fig, "RoLE minus k by spread and k (green clears, violet misses, white line = 0)",
      height=430)
fig.update_xaxes(range=[s_min, s_max], title_text="Client spread (bp)")
fig.update_yaxes(range=[k_min, k_max])
fig.update_yaxes(title_text="k (bp)", row=1, col=1)
fig.update_layout(coloraxis={"colorscale": DIVERGING, "cmin": -zmax, "cmax": zmax, "cmid": 0,
                             "colorbar": {"title": {"text": "RoLE − k (bp)"}, "thickness": 12,
                                          "outlinewidth": 0}},
                  plot_bgcolor=SURFACE, margin={"t": 115})
show(fig)
st.caption(" ".join(clearance_sentence(r, cap.loc[r], k) for r in ROUTES))
explain("spread vs k heatmaps", f"""
Each cell is RoLE(s) − k for client spread s (upgrade: fee) and balance-sheet charge k.
Dealer net is linear in the route's own spread, net(s) = a + b·s·τ, where b is the amount the
spread is charged on (PB loan, TRS notional, upgrade notional) and a = net(quoted) − b·s_quoted·τ.
Leverage exposure LE depends on neither s nor k, so

RoLE(s) = (a + b·s·τ) / (LE·τ), cell = RoLE(s) − k, τ = {x.tenor_days}/365.

Green cells clear (RoLE ≥ k), violet cells miss. The white line is RoLE = k, i.e. the required
spread at each k: s*(k) = (k·LE·τ − a) / (b·τ), a straight line along which the required
spread rises LE / b bp per bp of k. The route using the most leverage per GBP of spread base
needs the most extra spread as k rises (shallowest line). All three
panels share one symmetric colour scale (±{zmax:.0f} bp), so colours compare across routes. The
white dot is the quoted spread at the current k.
""")
