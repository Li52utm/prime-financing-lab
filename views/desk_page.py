from dataclasses import replace

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import assumptions as A
from engine.capital import (
    capital_comparison, return_on, trs_capital, trs_im_spread_for_hurdle, trs_saccr,
    trs_vs_im_remuneration,
)
from engine.financing import DEALER_PART_NAMES, pb_route, trs_route, upgrade_route
from ui.common import (
    MUTED, ROUTE_COLORS, ROUTE_PATTERNS, ROUTE_SYMBOLS, ROUTES, bp, explain, gbp,
    label, page_header, pct, route_line, show, style, table,
)
from ui.ticket import get_ctx, netting_trade

ctx = get_ctx()
x, c = ctx.fin, ctx.cap
page_header("Desk view", ctx)
cap = capital_comparison(x, c).set_index("route")
fins = {r.route: r for r in (pb_route(x), trs_route(x), upgrade_route(x))}
tau = x.tenor_days / A.DAYS_IN_YEAR

# --- Headlines ------------------------------------------------------------------------
cols = st.columns(3)
for col, route in zip(cols, ROUTES):
    r = cap.loc[route]
    with col.container(border=True):
        st.markdown(f"**{route}**")
        st.metric("Dealer net over tenor", gbp(r["dealer_net_gbp"]), delta_color="off")
        st.metric("Return on leverage exposure", bp(r["role"]),
                  f"{(r['role'] - x.shadow_cost_k) * 1e4:+.1f} bp vs k", delta_color="off")
        st.metric("Return on RWA", pct(r["rorwa"]),
                  f"{(r['rorwa'] - c.target_rorwa) * 100:+.2f} pp vs target", delta_color="off")
        explain(f"{route} desk returns", f"""
Dealer net = sum of the P&L components in the table below = **{gbp(r['dealer_net_gbp'])}**.

RoLE = dealer net / (leverage exposure × τ) = {gbp(r['dealer_net_gbp'])} /
({gbp(r['leverage_exposure_gbp'])} × {x.tenor_days}/365) = **{bp(r['role'])}**; hurdle k =
{pct(x.shadow_cost_k)}.

RoRWA = dealer net / (RWA × τ) = {gbp(r['dealer_net_gbp'])} / ({gbp(r['rwa_gbp'])} ×
{x.tenor_days}/365) = **{pct(r['rorwa'])}**; target {pct(c.target_rorwa)}. Both gross of the
shadow cost. RWA and leverage are illustrative (see Capital).
""")

# --- Dealer P&L decomposition ------------------------------------------------------------
st.subheader("Dealer P&L by component (GBP over the tenor)")
parts = pd.DataFrame({rt: fins[rt].dealer_parts for rt in ROUTES}).loc[list(DEALER_PART_NAMES)]
parts = parts[(parts != 0).any(axis=1)]
parts.loc["Dealer net"] = parts.sum()
parts.insert(0, "Component", [label(i) for i in parts.index])
table(parts, {rt: "gbp" for rt in ROUTES})
st.caption("SONIA from client and street funding largely offset; the net funding effect is the "
           "cash gap and the SONIA earned on client cash (reduced by IM remuneration).")

# --- Returns vs hurdles (two charts: different measures, no dual axis) -----------------
c1, c2 = st.columns(2)
with c1:
    fig = go.Figure(go.Bar(x=ROUTES, y=[cap.loc[r, "role"] * 1e4 for r in ROUTES],
                           marker_color=[ROUTE_COLORS[r] for r in ROUTES],
                           marker_pattern_shape=[ROUTE_PATTERNS[r] for r in ROUTES],
                           hovertemplate="%{x}: %{y:.1f} bp<extra></extra>"))
    fig.add_hline(y=x.shadow_cost_k * 1e4, line={"color": MUTED, "dash": "dash", "width": 1.5},
                  annotation_text=f"k {pct(x.shadow_cost_k)}", annotation_position="top left")
    show(style(fig, "Return on leverage exposure vs k", y_title="bp (annualised)", height=420))
with c2:
    fig = go.Figure(go.Bar(x=ROUTES, y=[cap.loc[r, "rorwa"] * 100 for r in ROUTES],
                           marker_color=[ROUTE_COLORS[r] for r in ROUTES],
                           marker_pattern_shape=[ROUTE_PATTERNS[r] for r in ROUTES],
                           hovertemplate="%{x}: %{y:.2f}%<extra></extra>"))
    fig.add_hline(y=c.target_rorwa * 100, line={"color": MUTED, "dash": "dash", "width": 1.5},
                  annotation_text=f"target {pct(c.target_rorwa)}", annotation_position="top left")
    show(style(fig, "Return on RWA vs target", y_title="% (annualised)", height=420))

# --- Quoted vs required spread --------------------------------------------------------
st.subheader("Quoted vs required spread")
fig = go.Figure()
for route in ROUTES:
    r = cap.loc[route]
    pts = {"Quoted": r["current_spread"], "Req. RoLE": r["required_spread_role"],
           "Req. RoRWA": r["required_spread_rorwa"]}
    fig.add_scatter(x=[v * 1e4 for v in pts.values()], y=[route] * 3, mode="lines+markers+text",
                    text=list(pts), textfont={"color": MUTED},
                    # Quoted below, required spreads above, so close values never collide
                    textposition=["bottom center", "top center", "top center"],
                    line=route_line(route)["line"],
                    marker={"size": [12, 12 if r["binding"] == "leverage" else 8,
                                     12 if r["binding"] == "RWA" else 8],
                            "color": ROUTE_COLORS[route], "symbol": ROUTE_SYMBOLS[route]},
                    name=route, hovertemplate="%{text}: %{x:.1f} bp<extra>" + route + "</extra>")
style(fig, "Quoted spread against the spread each target needs (binding marker larger)",
      x_title="bp over SONIA (upgrade: fee)", height=430)
fig.update_yaxes(range=[-0.7, 2.7])  # headroom so labels on the outer rows are not clipped
show(fig)
explain("required spreads", "Each required spread solves dealer net = target × denominator × τ, "
        "with RWA and leverage fixed (static notional). Binding = the higher of the two.")

# --- TRS vs IM remuneration ------------------------------------------------------------
st.subheader("TRS return against IM remuneration")
spreads = [s / 1e4 for s in range(0, int(x.sonia * 1e4) + 1, 25)]
im = trs_vs_im_remuneration(x, c, spreads)
s_star = trs_im_spread_for_hurdle(x, c)
fig = go.Figure()
fig.add_scatter(x=im["im_remuneration_spread"] * 1e4, y=im["role"] * 1e4, mode="lines+markers",
                name="TRS RoLE", **route_line("TRS"),
                hovertemplate="IM at SONIA − %{x:.0f} bp<br>RoLE %{y:.1f} bp<extra></extra>")
fig.add_hline(y=x.shadow_cost_k * 1e4, line={"color": MUTED, "dash": "dash", "width": 1.5},
              annotation_text=f"k {pct(x.shadow_cost_k)}", annotation_position="top left")
fig.add_vline(x=x.im_remuneration_spread * 1e4, line={"color": MUTED, "dash": "dot", "width": 1.5},
              annotation_text="current", annotation_position="bottom right")
show(style(fig, "TRS return on leverage exposure by IM remuneration spread",
           x_title="IM remuneration: SONIA minus (bp)", y_title="RoLE (bp)"))
in_range = s_star is not None and 0 <= s_star <= x.sonia
st.metric("IM spread at which TRS RoLE = k",
          bp(s_star) if s_star is not None else "n/a",
          "within 0 to SONIA" if in_range else "outside 0 to SONIA", delta_color="off")
explain("IM remuneration breakeven", f"""
The client earns SONIA − s on its cash IM of {gbp(x.notional * x.trs_im)}; the dealer pays it.
Dealer net rises by IM × Δs × τ for each increase in s, and leverage exposure does not change,
so s* = s + (k × LE × τ − net) / (IM × τ) = **{bp(s_star)}**.
""")
table(pd.DataFrame({
    "IM spread (bp)": im["im_remuneration_spread"] * 1e4,
    "Dealer net (GBP)": im["dealer_net_gbp"],
    "RoLE (bp)": im["role"] * 1e4,
    "TRS spread for RoLE = k (bp)": im["required_trs_spread_role"] * 1e4,
}), {"IM spread (bp)": "bp", "Dealer net (GBP)": "gbp", "RoLE (bp)": "bp",
     "TRS spread for RoLE = k (bp)": "bp"})

# --- Netting cases ----------------------------------------------------------------------
st.subheader("TRS netting set: three cases")
other_m = st.number_input("Client's other trade: short TRS notional (GBP m, hypothetical)",
                          min_value=0.0, max_value=1000.0, value=ctx.netting_notional / 1e6,
                          step=1.0, key="desk_netting_notional_m")
st.caption("Netting is recognised only under a legally enforceable netting agreement.")
cases = {
    "Standalone": (),
    "Netted: short on a different name": (netting_trade("different_name", other_m * 1e6),),
    "Netted: short on the same name": (netting_trade("same_name", other_m * 1e6),),
}
trs_net = fins["TRS"].dealer_net
rows = []
for case_name, trades in cases.items():
    cc = replace(c, netting_set=trades)
    sa, tc = trs_saccr(x, cc), trs_capital(x, cc)
    rows.append({"Case": case_name, "Equity add-on (GBP)": sa["addon"],
                 "Multiplier": sa["multiplier"], "EAD (GBP)": sa["ead"],
                 "RWA (GBP)": tc.rwa, "Leverage (GBP m)": tc.leverage_exposure / 1e6,
                 "TRS RoLE (bp)": return_on(trs_net, tc.leverage_exposure, tau) * 1e4})
table(pd.DataFrame(rows), {"Equity add-on (GBP)": "gbp", "Multiplier": "num", "EAD (GBP)": "gbp",
                           "RWA (GBP)": "gbp", "Leverage (GBP m)": "m", "TRS RoLE (bp)": "bp"})
explain("netting cases", f"""
SA-CCR equity add-on (PRA CCR (CRR) Art 280d): per name, AddOn_k = 32% × Σ(δ × notional × MF);
across names, √[(Σ 50% × AddOn_k)² + Σ(1 − 50%²) × AddOn_k²]. The dealer is short the TRS
(−{gbp(x.notional)}); the client's short TRS makes the dealer long (+{gbp(other_m * 1e6)}).
Same name: the positions offset inside one entity. Different name: only the systematic 50%
part offsets, so the add-on can rise. The whole trade's P&L is held fixed; only the capital
changes.
""")
