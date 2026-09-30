import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import assumptions as A
from engine.capital import best_for_desk, capital_comparison, k_sensitivity
from engine.financing import breakeven_trs_spread, pb_route, trs_route, upgrade_route
from ui.common import (
    ROUTE_COLORS, ROUTES, bp, explain, gbp, over_sonia_bp, page_header, pct, show, style, table,
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
            "No best-for-desk route is named.", icon=":material/block:")
else:
    st.success(f"Clears k = {pct(k)}: {best} has the highest return on leverage exposure "
               "among routes that clear.", icon=":material/check_circle:")

# --- Lead: break-even k and required vs quoted spread, per route -------------------
st.subheader("Break-even balance-sheet charge and required spread")
cols = st.columns(3)
for col, route in zip(cols, ROUTES):
    row = cap.loc[route]
    lever = "fee" if route == "Collateral upgrade" else "spread"
    with col.container(border=True):
        st.markdown(f"**{route}**")
        be = row["break_even_k"]
        st.metric("Break-even k", bp(be), f"{(be - k) * 1e4:+.1f} bp vs k", delta_color="normal")
        st.metric(f"Required {lever} for RoLE = k", bp(row["required_spread_role"]),
                  f"quoted {bp(row['current_spread'])}", delta_color="off")
        clears = bool(row["clears_role_hurdle"])
        st.markdown(("✅ **Clears k**" if clears else "❌ **Misses k**")
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
                    mode="lines+markers", line={"color": ROUTE_COLORS[route], "width": 2},
                    marker={"size": 8},
                    hovertemplate="k %{x:.2f}%<br>required %{y:.1f} bp<extra>" + route + "</extra>")
    fig.add_scatter(x=[ks["k"].min() * 100, ks["k"].max() * 100],
                    y=[cap.loc[route, "current_spread"] * 1e4] * 2, name=f"{route} quoted",
                    mode="lines", line={"color": ROUTE_COLORS[route], "width": 2, "dash": "dot"},
                    hovertemplate="quoted %{y:.1f} bp<extra>" + route + "</extra>")
fig.add_vline(x=k * 100, line={"color": "#898781", "width": 1, "dash": "dash"},
              annotation_text=f"k = {pct(k)}", annotation_position="top")
show(style(fig, "Required spread for RoLE = k, against quoted (dotted)",
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
