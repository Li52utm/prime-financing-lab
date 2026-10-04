"""Replay history: run the ticket's TRS day by day over real equity history using the existing
capital engine, check supervisory haircuts against actual 10-day losses, and compare a
volatility-implied IM with the static ticket IM. Illustrative and simplified throughout."""

from dataclasses import replace
from statistics import NormalDist

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import assumptions as A
from analytics import replay as R
from data import markets as M
from engine.capital import equity_haircut_10d
from engine.financing import trs_route
from ui.common import (ACCENT, MKT, MUTED, OTHER_COLORS, explain, gbp, gbp_m, page_header, pct,
                       show, style, table)
from ui.ticket import get_ctx

ctx = get_ctx()
page_header("Replay history", ctx)
st.info("**Illustrative and simplified.** Real closing prices drive the ticket's TRS through the "
        "app's capital engine (SA-CCR-style exposure, RWA and leverage are simplified, not a "
        "regulatory calculation). This replays what happened; it says nothing about what will.")

EQUITIES = ["ftse100", "spx"]


@st.cache_data(ttl=A.MARKETS_CACHE_TTL_HOURS * 3600, show_spinner="Fetching equity history...")
def equity(key: str) -> M.MarketSeries:
    return M.load_series(key)


c1, c2, c3 = st.columns([2, 3, 2])
key = c1.selectbox("Equity index", EQUITIES, format_func=lambda k: M.SERIES[k].name, key="rp_eq")
presets = list(A.REPLAY_PRESETS) + ["Custom dates"]
preset = c2.selectbox("Window (historical dates)", presets,
                      index=presets.index(A.REPLAY_DEFAULT_PRESET), key="rp_preset")
size_m = c3.number_input("Trade size (GBP m)", min_value=1.0, max_value=5000.0,
                         value=float(ctx.fin.notional / 1e6), step=1.0, key="rp_size")
margined = st.toggle("TRS margined daily (cash VM)", value=ctx.cap.trs_margined, key="rp_margined")

try:
    series = equity(key)
except M.MarketDataError as e:
    st.error(f"No data for {M.SERIES[key].name}. {e}")
    st.stop()
spec = series.spec
close = series.data["close"]
first, last = close.index[0].date(), close.index[-1].date()
if preset == "Custom dates":
    d1, d2 = st.columns(2)
    start = d1.date_input("Start", value=max(first, pd.Timestamp(A.REPLAY_CUSTOM_DEFAULT_START).date()),
                          min_value=first, max_value=last, key="rp_start")
    end = d2.date_input("End", value=last, min_value=first, max_value=last, key="rp_end")
else:
    start, end = (pd.Timestamp(d).date() for d in A.REPLAY_PRESETS[preset])
if series.status == "cached":
    st.warning(f"Live fetch failed; using the cached copy fetched "
               f"{series.fetched_at[:16].replace('T', ' ')}.")
st.caption(f"Prices: {spec.source}, daily closes, {first:%d %b %Y} to {last:%d %b %Y} (as of "
           f"{series.as_of:%d %b %Y}, {series.status}). Yahoo Finance is not an official "
           "provider; terms unverified. Index levels stand in for the TRS underlying.")

prices = R.window(close, start, end)
if pd.Timestamp(start) < close.index[0] or len(prices) < 2:
    st.error(f"The data for {spec.name} does not cover {start:%d %b %Y} to {end:%d %b %Y} "
             f"(history runs {first:%d %b %Y} to {last:%d %b %Y}). Nothing is replayed.")
    st.stop()

x = replace(ctx.fin, notional=size_m * 1e6)
c = ctx.cap
path = R.replay_trs(prices, x, c, margined)
sm = R.replay_summary(path)
stamp = f"Daily · {spec.source} · as of {series.as_of:%d %b %Y}"

# --- Headline numbers ------------------------------------------------------------------------
st.subheader(f"TRS replay: {spec.name}, {prices.index[0]:%d %b %Y} to {prices.index[-1]:%d %b %Y}")
m = st.columns(5)
m[0].metric("Worst day", f"{sm['worst_day']:%d %b %Y}", f"{sm['worst_return'] * 100:+.2f}% stock",
            delta_color="off", delta_arrow="off")
m[1].metric("VM call that day", gbp_m(sm["worst_vm_call"]) if margined else "n/a",
            None if margined else "unmargined", delta_color="off", delta_arrow="off")
m[2].metric("Peak EAD", gbp_m(sm["peak_ead"]), f"on {sm['peak_day']:%d %b %Y}",
            delta_color="off", delta_arrow="off")
m[3].metric("Peak RWA", gbp_m(sm["max_rwa"]))
m[4].metric("Dealer financing P&L", gbp(sm["end_pnl"]))
st.caption(f"{len(path):,} trading days. Trade struck at the first close ({prices.iloc[0]:,.2f}) "
           f"with notional {gbp_m(x.notional)} and ticket IM {pct(x.trs_im, 1)} "
           f"({gbp_m(x.notional * x.trs_im)}). Lowest point {sm['trough_move'] * 100:+.1f}% from the "
           f"strike. Margining: {'daily cash VM' if margined else 'none (RC grows once V exceeds IM)'}.")

# --- Path chart -----------------------------------------------------------------------------
fig = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.045,
                    row_heights=[0.19, 0.23, 0.23, 0.17, 0.18],
                    subplot_titles=[f"{spec.name} close (index points)",
                                    "TRS value V, VM calls and cash held (GBP m)",
                                    "Counterparty exposure: RC, add-on, EAD and RWA (GBP m)",
                                    "Leverage exposure (GBP m)",
                                    "Cumulative dealer financing P&L (GBP)"])
mm = 1e6
fig.add_trace(go.Scatter(x=path.index, y=path["close"], name="Close", mode="lines",
                         line={"color": ACCENT, "width": 2.2}), row=1, col=1)
fig.add_trace(go.Bar(x=path.index, y=path["vm_call"] / mm, name="VM call (+ client pays)",
                     marker_color=MKT["band"], opacity=0.8), row=2, col=1)
fig.add_trace(go.Scatter(x=path.index, y=path["v"] / mm, name="V (dealer side)", mode="lines",
                         line={"color": MKT["ma_fast"], "width": 2.4}), row=2, col=1)
fig.add_trace(go.Scatter(x=path.index, y=path["cash_held"] / mm, name="Cash held (IM + VM)",
                         mode="lines", line={"color": OTHER_COLORS[0], "width": 2.4, "dash": "dash"}),
              row=2, col=1)
for col, name, color, dash in (("rc", "RC", OTHER_COLORS[2], "solid"),
                               ("addon", "Add-on", OTHER_COLORS[1], "dot"),
                               ("ead", "EAD", ACCENT, "solid"), ("rwa", "RWA", MKT["ma_fast"], "dash")):
    fig.add_trace(go.Scatter(x=path.index, y=path[col] / mm, name=name, mode="lines",
                             line={"color": color, "width": 2.2, "dash": dash}), row=3, col=1)
fig.add_trace(go.Scatter(x=path.index, y=path["leverage"] / mm, name="Leverage exposure",
                         mode="lines", line={"color": MKT["band"], "width": 2.2}), row=4, col=1)
fig.add_trace(go.Scatter(x=path.index, y=path["cum_pnl"], name="Cumulative financing P&L (GBP)",
                         mode="lines", line={"color": ACCENT, "width": 2.2, "dash": "dash"}),
              row=5, col=1)
for r_ in range(1, 6):
    fig.add_vline(x=sm["worst_day"].value / 1e6, line={"color": MUTED, "dash": "dot", "width": 1.5},
                  row=r_, col=1)
fig.add_trace(go.Scatter(x=[sm["peak_day"]], y=[sm["peak_ead"] / mm], mode="markers",
                         name="Peak EAD", marker={"symbol": "diamond", "size": 13,
                                                  "color": OTHER_COLORS[2],
                                                  "line": {"color": "#000", "width": 1}}),
              row=3, col=1)
fig.update_layout(hovermode="x unified", barmode="relative")
style(fig, f"{spec.name}: TRS replay, GBP ({'margined' if margined else 'unmargined'})",
      height=1300, subtitle=stamp)
fig.update_layout(margin={"t": 118})
show(fig)
st.caption(f"Dotted vertical line: worst day ({sm['worst_day']:%d %b %Y}, "
           f"{sm['worst_return'] * 100:+.2f}%). Diamond: peak EAD. V > 0 means the client owes the "
           "dealer (the stock fell; the dealer pays the equity return). Illustrative and simplified.")

with st.expander("Daily path (table and CSV)"):
    out = path.reset_index()
    out["date"] = out["date"].dt.date
    table(out, {"close": "num2", "move": "pct", "v": "gbp", "vm_call": "gbp", "im_call": "gbp",
                "cash_held": "gbp", "rc": "gbp", "multiplier": "num", "addon": "gbp",
                "ead": "gbp", "rwa": "gbp", "leverage": "gbp", "cum_pnl": "gbp"}, height=420)
    st.download_button("Download the path as CSV", out.to_csv(index=False).encode("utf-8"),
                       file_name=f"trs_replay_{key}_{start:%Y%m%d}_{end:%Y%m%d}.csv",
                       mime="text/csv", key="rp_csv")

explain("the replay", f"""
Each trading day t with close P_t (strike P_0 = first close of the window):
- move m_t = P_t / P_0 − 1; **V_t = −N × m_t** (engine `trs_mtm_from_price_move`).
- **VM call** = V_t − V_(t−1) when margined (positive: the client pays); **IM call** = N × IM on
  day one only (ticket IM, static). **Cash held** = IM + cumulative VM.
- **RC, multiplier, add-on, EAD**: engine `trs_saccr` with V_t and m_t (PRA CCR (CRR) Art
  274-280d; illustrative). **RWA, leverage**: engine `trs_capital` (Art 429b-429e; illustrative).
- **Dealer financing P&L** = the ticket's TRS dealer net ({gbp_m(trs_route(x).dealer_net)} over
  {x.tenor_days} days) accrued per calendar day.
""")
with st.expander("Simplifications (read before using these numbers)"):
    st.markdown(R.__doc__.split("Simplifications, all stated on the page:")[1])

# --- Empirical haircut check -----------------------------------------------------------------
h = A.REPLAY_HAIRCUT_HORIZON_DAYS
st.subheader(f"Empirical haircut check: actual {h}-day losses vs supervisory haircuts")
losses_all = R.forward_losses(close, h)
haircuts = {A.HAIRCUT_REGIMES[r]["label"].split(" (")[0]: equity_haircut_10d(r, c.haircut_class)
            for r in A.HAIRCUT_REGIMES}
scopes = {"Full history": losses_all,
          "Selected window": losses_all[(losses_all.index >= pd.Timestamp(start))
                                        & (losses_all.index <= pd.Timestamp(end))]}
rows = []
for scope, ls in scopes.items():
    if len(ls) == 0:
        continue
    for _, r in R.haircut_check(ls, haircuts, h).iterrows():
        rows.append({"Scope": scope, "Regime": r["regime"], "Haircut": r["haircut"] * 100,
                     "Windows": r["windows"], "Breaches": r["breaches"], "Breach %": r["breach_pct"],
                     "Blocks": r["blocks"], "Block breaches": r["block_breaches"],
                     "Worst loss": r["worst_loss"] * 100, "Worst start": r["worst_start"].date()})
table(pd.DataFrame(rows), {"Haircut": "pct", "Windows": "int", "Breaches": "int", "Breach %": "pct",
                           "Blocks": "int", "Block breaches": "int", "Worst loss": "pct"})
fig = go.Figure()
fig.add_trace(go.Scatter(x=losses_all.index, y=losses_all * 100, mode="lines",
                         name=f"{h}-day loss from each start date",
                         line={"color": MKT["band"], "width": 1.4},
                         hovertemplate="%{x|%d %b %Y}<br>loss %{y:.1f}%<extra></extra>"))
for i, (label, hc) in enumerate(haircuts.items()):
    fig.add_hline(y=hc * 100, line={"color": [MKT["ma_fast"], OTHER_COLORS[0]][i % 2], "width": 2,
                                    "dash": ["dash", "dot"][i % 2]},
                  annotation_text=f"{label}: {hc * 100:.0f}%",
                  annotation_position="top left" if i % 2 == 0 else "bottom left")
style(fig, f"{spec.name}: {h}-trading-day losses vs supervisory equity haircuts, %",
      y_title="Loss over next 10 trading days (%)", height=460, subtitle=stamp)
show(fig)
st.caption(f"Loss = 1 − P(t+{h}) / P(t) over the next {h} trading days, from every start date "
           f"(overlapping windows, so breaches cluster) and from every {h}th date (Blocks: non-overlapping). "
           "Haircut, Breach % and Worst loss are in %. "
           f"Haircut class: {c.haircut_class.replace('_', ' ')} (from the ticket's asset class). "
           "Supervisory haircuts: PRA CRM (CRR) Art 224(1) Table 3 (Basel 3.1) and UK CRR Art 224 "
           "Table 3 (current), as set in assumptions.py. An index is more diversified than a "
           "single stock, so single names breach more often than this.")

# --- Volatility-implied IM -------------------------------------------------------------------
st.subheader("Volatility-implied IM vs the static ticket IM")
hi = A.REPLAY_IM_HORIZON_DAYS
vol = R.ewma_vol(close, A.REPLAY_EWMA_LAMBDA, A.REPLAY_EWMA_BURN_IN)
vim = R.vol_implied_im(vol, A.REPLAY_IM_CONFIDENCE, hi).dropna()
bt = R.im_backtest(vim, x.trs_im, R.forward_losses(close, hi))
fig = go.Figure()
fig.add_trace(go.Scatter(x=vim.index, y=vim * 100, mode="lines",
                         name=f"EWMA {A.REPLAY_IM_CONFIDENCE:.0%} {hi}-day IM",
                         line={"color": ACCENT, "width": 1.8},
                         hovertemplate="%{x|%d %b %Y}<br>IM %{y:.1f}% of notional<extra></extra>"))
fig.add_hline(y=x.trs_im * 100, line={"color": MKT["ma_fast"], "width": 2.2, "dash": "dash"},
              annotation_text=f"Ticket IM {x.trs_im * 100:.0f}%", annotation_position="top left")
for d in (start, end):
    fig.add_vline(x=pd.Timestamp(d).value / 1e6, line={"color": MUTED, "width": 1, "dash": "dot"})
style(fig, f"{spec.name}: volatility-implied IM vs static ticket IM, % of notional",
      y_title="% of notional", height=440, subtitle=stamp)
show(fig)
st.caption(f"IM_t = z × σ_t × √{hi}, z = {NormalDist().inv_cdf(A.REPLAY_IM_CONFIDENCE):.3f} "
           f"({A.REPLAY_IM_CONFIDENCE:.0%} one-tailed normal), σ_t = EWMA daily volatility of log "
           f"returns (λ = {A.REPLAY_EWMA_LAMBDA}, RiskMetrics; first {A.REPLAY_EWMA_BURN_IN} days "
           f"dropped), using returns up to day t only. Over {bt['days']:,} days: the next {hi}-day "
           f"loss exceeded the EWMA IM on {bt['vol_breaches']:,} days "
           f"({bt['vol_breaches'] / bt['days'] * 100:.2f}%) and the static ticket IM on "
           f"{bt['static_breaches']:,} days ({bt['static_breaches'] / bt['days'] * 100:.2f}%); a "
           f"{A.REPLAY_IM_CONFIDENCE:.0%} model aims for about {(1 - A.REPLAY_IM_CONFIDENCE) * 100:.0f}%. "
           f"EWMA IM was above the ticket IM on {bt['vol_above_static_pct']:.1f}% of days. Dotted "
           "lines mark the replay window. Illustrative; the confidence and horizon follow the "
           "BCBS-IOSCO uncleared-margin benchmark (paragraph UNVERIFIED).")
