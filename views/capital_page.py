from dataclasses import replace

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import assumptions as A
from engine.capital import (
    NOT_MODELLED_BANNER, equity_haircut_10d, pb_capital, pb_rwa_by_margin,
    return_on, scaled_haircut, trs_capital, trs_saccr, upgrade_capital,
)
from engine.financing import GILT_SOURCES, upgrade_route
from ui.common import (
    MUTED, OTHER_COLORS, ROUTES, SURFACE, explain, gbp, gbp_m, page_header, pct,
    label, route_line, show, style, table,
)
from ui.ticket import GILT_SOURCE_LABELS, get_ctx

ctx = get_ctx()
x, c = ctx.fin, ctx.cap
st.error(NOT_MODELLED_BANNER)
page_header("Capital", ctx)
tau = x.tenor_days / A.DAYS_IN_YEAR
caps = {r.route: r for r in (pb_capital(x, c), trs_capital(x, c), upgrade_capital(x, c))}

# --- Headlines -------------------------------------------------------------------------
cols = st.columns(3)
for col, route in zip(cols, ROUTES):
    r = caps[route]
    with col.container(border=True):
        st.markdown(f"**{route}**")
        st.metric("Leverage exposure", gbp_m(r.leverage_exposure), delta_color="off")
        st.metric("RWA", gbp_m(r.rwa), delta_color="off")
        lev = "\n".join(f"- {label(k)}: {gbp(v)}" for k, v in r.leverage_parts.items()
                        if v)
        rwa = "\n".join(f"- {label(k)}: EAD {gbp(r.ead_parts[k])} → RWA {gbp(v)}"
                        for k, v in r.rwa_parts.items())
        explain(f"{route} leverage and RWA", f"""
**Leverage exposure** (PRA Leverage Ratio (CRR) Art 429b, 429c, 429e; illustrative):

{lev}

**RWA** = Σ exposure × risk weight (client {pct(c.rw_client, 0)}, street {pct(c.rw_street, 0)};
own assumptions, UNVERIFIED):

{rwa}

SFT exposures use the comprehensive approach (PRA CRM (CRR) Art 223-224); TRS uses SA-CCR
(PRA CCR (CRR) Art 274-280d). See the route's T-account below.
""")

# --- RWA and leverage by component (two charts, one measure each) -------------------------
RWA_GROUPS = {"client": "Client", "client_saccr": "Client", "street_repo": "Street repo",
              "reverse_repo": "Reverse repo cpty", "gilt_lender": "Gilt lender"}
LEV_GROUPS = {"margin_loan": "On-sheet assets", "hedge_stock": "On-sheet assets",
              "reverse_repo_receivable": "On-sheet assets", "surplus_cash": "On-sheet assets",
              "derivative": "Derivative 1.4×(RC+PFE)"}


def stacked(parts_by_route: dict, groups: dict, default: str, title: str, y_title: str):
    order = list(dict.fromkeys([*groups.values(), default]))
    data = {g: [0.0] * len(ROUTES) for g in order}
    for i, route in enumerate(ROUTES):
        for k, v in parts_by_route[route].items():
            data[groups.get(k, default)][i] += v / 1e6
    fig = go.Figure()
    for j, g in enumerate(g for g in order if any(data[g])):
        fig.add_bar(x=ROUTES, y=data[g], name=g, marker_color=OTHER_COLORS[j % 4],
                    marker_line={"color": SURFACE, "width": 2},
                    hovertemplate="%{x}<br>" + g + ": £%{y:.2f}m<extra></extra>")
    fig.update_layout(barmode="stack")
    show(style(fig, title, y_title=y_title, height=440))


c1, c2 = st.columns(2)
with c1:
    stacked({r: caps[r].rwa_parts for r in ROUTES}, RWA_GROUPS, "Other", "RWA by counterparty",
            "GBP m")
with c2:
    stacked({r: caps[r].leverage_parts for r in ROUTES}, LEV_GROUPS, "SFT add-ons",
            "Leverage exposure by component", "GBP m")

# --- T-accounts ----------------------------------------------------------------------------
st.subheader("Dealer T-accounts (incremental, one trade)")
cols = st.columns(3)
for col, route in zip(cols, ROUTES):
    ta = caps[route].t_account
    with col:
        st.markdown(f"**{route}**")
        for side in ("assets", "liabilities"):
            items = {k: v for k, v in ta[side].items() if v}
            df = pd.DataFrame({side.capitalize(): list(items) or ["(none)"],
                               "GBP": list(items.values()) or [0.0]})
            table(df, {"GBP": "gbp"})
st.caption("Client stock received as collateral, and gilts received and re-delivered, are off "
           "the dealer's balance sheet. Surplus cash at the central bank is netted out of the "
           "leverage exposure (PRA Leverage Ratio (CRR) Art 429a).")

# --- Gilt source side by side --------------------------------------------------------------
st.subheader("Collateral upgrade: how the dealer sources the gilts")
rows = []
for src in GILT_SOURCES:
    xs = replace(x, gilt_source=src)
    u, uc = upgrade_route(xs), upgrade_capital(xs, c)
    rows.append({"Gilt source": GILT_SOURCE_LABELS[src] + (" (selected)" if src == x.gilt_source
                                                           else ""),
                 "Dealer net (GBP)": u.dealer_net, "Leverage (GBP m)": uc.leverage_exposure / 1e6,
                 "RWA (GBP m)": uc.rwa / 1e6, "HQLA change (GBP m)": uc.hqla_change / 1e6,
                 "RoLE (bp)": (return_on(u.dealer_net, uc.leverage_exposure, tau) or float("nan"))
                 * 1e4})
table(pd.DataFrame(rows), {"Dealer net (GBP)": "gbp", "Leverage (GBP m)": "m", "RWA (GBP m)": "m",
                           "HQLA change (GBP m)": "m", "RoLE (bp)": "bp"})
explain("gilt sources", f"""
- **Reverse repo**: the dealer lends cash R = G(1 − {pct(x.gilt_haircut, 0)}) against gilts and
  funds it by repoing the client's equities; R sits on the balance sheet.
- **Borrowed**: securities for securities, off balance sheet; leverage is the SFT add-on
  max(0, N − G) to the gilt lender (Art 429e).
- **Inventory**: the dealer's own gilts, already on the balance sheet; the cost shows up as HQLA
  used: −G + 50% × N if the equity is Level 2B (UNVERIFIED, illustrative).
RoLE is n/a when leverage exposure is zero.
""")

# --- PB RWA vs margin ------------------------------------------------------------------------
st.subheader("PB: RWA against client margin")
margins = [m / 100 for m in range(5, 51)]
pbm = pb_rwa_by_margin(x, c, margins)
h10 = equity_haircut_10d(c.haircut_regime, c.haircut_class)
h_pb = scaled_haircut(h10, c.pb_liquidation_days)
fig = go.Figure()
fig.add_scatter(x=pbm["pb_margin"] * 100, y=pbm["rwa"] / 1e6, mode="lines", name="RWA",
                line=route_line("PB")["line"],
                hovertemplate="margin %{x:.0f}%<br>RWA £%{y:.2f}m<extra></extra>")
fig.add_vline(x=h_pb * 100, line={"color": MUTED, "dash": "dash", "width": 1.5},
              annotation_text=f"supervisory haircut {pct(h_pb, 1)}", annotation_position="top right")
fig.add_vline(x=x.pb_margin * 100, line={"color": MUTED, "dash": "dot", "width": 1.5},
              annotation_text=f"margin {pct(x.pb_margin, 0)}", annotation_position="top left")
show(style(fig, "PB RWA by client margin", x_title="Client margin (% of notional)",
           y_title="RWA (GBP m)"))
explain("PB RWA vs margin", f"""
Client exposure E* = max(0, L − N(1 − H)), L = N(1 − margin), H = {pct(h10, 0)} × √({c.pb_liquidation_days}/10)
= {pct(h_pb, 2)} (PRA CRM (CRR) Art 224, {A.HAIRCUT_REGIMES[c.haircut_regime]['label']}).
Above the haircut the client exposure is zero; the rest is the street repo leg.
""")

# --- SA-CCR detail ---------------------------------------------------------------------------
with st.expander("TRS SA-CCR detail"):
    sa = trs_saccr(x, c)
    table(pd.DataFrame([{
        "Maturity factor": sa["mf"], "Equity add-on (GBP)": sa["addon"],
        "NICA (GBP)": sa["nica"], "RC (GBP)": sa["rc"], "Multiplier": sa["multiplier"],
        "PFE (GBP)": sa["pfe"], "EAD (GBP)": sa["ead"]}]),
        {"Maturity factor": "num", "Equity add-on (GBP)": "gbp", "NICA (GBP)": "gbp",
         "RC (GBP)": "gbp", "Multiplier": "num", "PFE (GBP)": "gbp", "EAD (GBP)": "gbp"})
    st.markdown("EAD = 1.4 × (RC + multiplier × AddOn). PRA CCR (CRR) Art 274(2), 275, 278(3), "
                "279c, 280d. Maturity uses days/365 in place of business-day years.")
