import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import assumptions as A
from engine.stress import (
    VIEW_LABELS, all_presets, get_preset, price_shock_table, repricing_path, stress_comparison,
    term_vs_rolling_by_preset,
)
from ui.common import (
    explain, gbp, other_line, page_header, show, style, table,
)
from ui.ticket import get_ctx

ctx = get_ctx()
x, c = ctx.fin, ctx.cap
page_header("Stress lab", ctx)
st.info("Every preset and shock here is **hypothetical**: an own assumption chosen to show the "
        "mechanics, not a forecast.")

# --- Presets ------------------------------------------------------------------------------
st.subheader("Stress presets (hypothetical)")
names = [p.name for p in all_presets()]
c1, c2, c3 = st.columns([3, 4, 3])
name = c1.selectbox("Preset", names, format_func=lambda n: get_preset(n).label.replace(" (hypothetical)", ""),
                   key="preset")  # section heading and caption say hypothetical
view = c2.radio("Horizon", list(VIEW_LABELS), format_func=VIEW_LABELS.get, key="view")
pb_rep = c3.slider("PB repriced (% of client shock)", 0, 100, 0, step=25, key="pb_rep") / 100
p = get_preset(name)
st.caption(f"**{p.label}: {VIEW_LABELS[view]}.** Client spread +{p.client_spread_shock * 1e4:.0f} "
            f"bp, street spread +{p.street_spread_shock * 1e4:.0f} bp, k +{p.k_shock * 100:.2f}%, "
            f"street haircut +{p.street_haircut_change * 100:.0f}%, gilt borrow "
            f"+{p.gilt_borrow_shock * 1e4:.0f} bp, turn {p.turn_days} days.")
s = stress_comparison(x, c, p, pb_repriced=pb_rep, view=view)
table(pd.DataFrame({
    "Route": s["route"],
    "Net base": s["dealer_net_base"],
    "Net stressed": s["dealer_net_stressed"],
    "Street shock": s["street_shock_cost"],
    "Client repricing": s["client_repricing_income"],
    "RoLE": s["role_stressed"] * 1e4,
    "k": s["k_stressed"] * 1e4,
    "Req. spread": s["required_spread_role_stressed"] * 1e4,
    "Clears": s["clears_role_hurdle_stressed"].map({True: "Yes", False: "No"}),
}), {"Net base": "gbp", "Net stressed": "gbp", "Street shock": "gbp", "Client repricing": "gbp",
     "RoLE": "bp", "k": "bp", "Req. spread": "bp"})
st.caption("Dealer net, street shock cost and client repricing in GBP over the tenor; stressed "
           "RoLE, stressed k and the required spread in bp.")
explain("stressed dealer net", f"""
k, street haircut and gilt borrow shocks apply for the whole tenor. The street spread shock is
charged for **{int(s['street_shock_days'].iloc[0])} days** and the client repricing credited for
**{int(s['client_repricing_days'].iloc[0])} days** (view: {VIEW_LABELS[view]}), each as
amount × shock × days / 365. PB has repriced {pb_rep:.0%} of the client shock; TRS and upgrade
fully. The required spread excludes client-repricing income, so it is comparable across views.
""")

# --- Price shock -----------------------------------------------------------------------------
st.subheader("Stock price shock: TRS counterparty exposure")
ps = price_shock_table(x, c)
fig = go.Figure()
for j, (col, label) in enumerate([("ead", "EAD"), ("rwa", "RWA")]):
    fig.add_scatter(x=ps["price_move"] * 100, y=ps[col] / 1e6, name=label, mode="lines+markers",
                    **other_line(j),
                    hovertemplate="move %{x:.0f}%<br>" + label + " £%{y:.2f}m<extra></extra>")
show(style(fig, "TRS EAD and RWA by stock move (hypothetical grid)", x_title="Stock move (%)",
           y_title="GBP m"))
table(pd.DataFrame({
    "Move (%)": ps["price_move"] * 100, "V (GBP)": ps["mtm_v"], "RC (GBP)": ps["rc"],
    "Multiplier": ps["multiplier"], "EAD (GBP)": ps["ead"], "RWA (GBP)": ps["rwa"],
    "Leverage (GBP m)": ps["leverage_exposure"] / 1e6,
}), {"Move (%)": "pct", "V (GBP)": "gbp", "RC (GBP)": "gbp", "Multiplier": "num",
     "EAD (GBP)": "gbp", "RWA (GBP)": "gbp", "Leverage (GBP m)": "m"})
explain("price shock", f"""
V = −N × move (the dealer pays the equity return, so a fall is owed to the dealer). The hedge
and the SA-CCR adjusted notional scale by (1 + move) (PRA CCR (CRR) Art 279b(1)(c), TRS on a
number of shares: {'yes' if c.trs_notional_in_units else 'no'}). RC = max(V − IM, 0) unmargined;
the multiplier reaches 1 once V exceeds the IM of {gbp(x.notional * x.trs_im)}. Street repo cash
and IM stay at their original amounts.
""")

# --- Repricing lag ----------------------------------------------------------------------------
st.subheader("Pass-through lag: TRS reprices at once, PB by month")
f = st.slider("PB repricing per month (%)", 5, 100,
              int(A.PB_REPRICING_FRACTION_PER_MONTH * 100), step=5, key="pb_per_month") / 100
path = repricing_path(x, p, fraction_per_month=f)
fig = go.Figure()
for j, (col, label) in enumerate([("cum_cost_gap", "Cumulative client cost gap (PB − TRS)"),
                                  ("cum_dealer_pb_shortfall", "Cumulative dealer PB shortfall")]):
    fig.add_scatter(x=path["month"], y=path[col], name=label, mode="lines+markers",
                    **other_line(j),
                    hovertemplate="month %{x}<br>£%{y:,.0f}<extra>" + label + "</extra>")
show(style(fig, f"{p.label}: shock persists for the whole path", x_title="Month after shock",
           y_title="GBP"))
table(pd.DataFrame({
    "Month": path["month"], "PB repriced (%)": path["pb_repriced_fraction"] * 100,
    "Cost gap PB − TRS (GBP)": path["cost_gap"], "Cumulative gap (GBP)": path["cum_cost_gap"],
    "PB dealer net (GBP)": path["dealer_net_pb"], "TRS dealer net (GBP)": path["dealer_net_trs"],
    "Cum. PB shortfall (GBP)": path["cum_dealer_pb_shortfall"],
}), {"Month": "int", "PB repriced (%)": "pct", "Cost gap PB − TRS (GBP)": "gbp",
     "Cumulative gap (GBP)": "gbp", "PB dealer net (GBP)": "gbp", "TRS dealer net (GBP)": "gbp",
     "Cum. PB shortfall (GBP)": "gbp"})
explain("repricing lag", f"""
Each month ({A.MONTH_DAYS} days) is priced with that month's spreads. PB passes through
min(1, {f:.0%} × month) of the client shock; the TRS all of it from day one. The street shock hits
the dealer at once. After full repricing the gap does not return to its pre-shock level: it
moves by −(N − L) × client shock × τ, because PB reprices on its loan L and the TRS on N.
""")

# --- Term vs rolling -------------------------------------------------------------------------
st.subheader("Street funding: lock term or roll through the turn")
tv = term_vs_rolling_by_preset(x)
table(pd.DataFrame({
    "Preset": tv["label"], "Amount (GBP)": tv["amount"], "Turn (days)": tv["turn_days"],
    "Turn shock (bp)": tv["turn_shock"] * 1e4, "Term premium (bp)": tv["term_premium"] * 1e4,
    "Breakeven premium (bp)": tv["breakeven_term_premium"] * 1e4,
    "Rolling cost (GBP)": tv["rolling_cost"], "Term cost (GBP)": tv["term_cost"],
    "Term saving (GBP)": tv["term_saving"], "Cheaper": tv["cheaper"],
}), {"Amount (GBP)": "gbp", "Turn (days)": "int", "Turn shock (bp)": "bp",
     "Term premium (bp)": "bp", "Breakeven premium (bp)": "bp", "Rolling cost (GBP)": "gbp",
     "Term cost (GBP)": "gbp", "Term saving (GBP)": "gbp"})
explain("term vs rolling", f"""
Over {A.TERM_HORIZON_DAYS} days on the dealer's street funding N(1 − h_st): rolling pays the
base spread plus the shock for the turn days; term pays base + term premium throughout.
Breakeven premium = shock × turn days / horizon. SONIA is common to both and excluded.
""")
