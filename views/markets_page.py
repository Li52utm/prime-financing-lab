"""Markets: daily history with a trader-style indicator stack. Display analytics only; nothing
here feeds the financing engine."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import assumptions as A
from analytics import indicators as I
from data import markets as M
from ui.common import ACCENT, MKT, MUTED, explain, show, style, table

st.caption("Public market data for context. Display analytics only: none of this feeds the "
           "financing engine.")


@st.cache_data(ttl=A.MARKETS_CACHE_TTL_HOURS * 3600, show_spinner="Fetching market data...")
def cached_series(key: str) -> M.MarketSeries:
    return M.load_series(key)  # raises MarketDataError (not cached) if live and cache fail


# --- Controls ------------------------------------------------------------------------------
c1, c2 = st.columns([2, 3])
key = c1.selectbox("Asset", list(M.SERIES), format_func=lambda k: M.SERIES[k].name,
                   key="mkt_asset")
ranges = list(A.MARKETS_RANGES_MONTHS)
rng = c2.radio("Range", ranges, index=ranges.index(A.MARKETS_DEFAULT_RANGE), horizontal=True,
               key="mkt_range")
with st.expander("Indicator settings"):
    s1, s2 = st.columns(2)
    bb_window = int(s1.number_input("Bollinger window (days)", 5, 200, A.MARKETS_BB_WINDOW, 1,
                                    key="mkt_bb_window"))
    bb_width = float(s2.number_input("Bollinger width (std devs)", 0.5, 4.0, A.MARKETS_BB_WIDTH,
                                     0.25, key="mkt_bb_width"))
    log_axis = st.toggle("Log scale for the price panel (price series only)", value=False,
                         key="mkt_log")

spec = M.SERIES[key]
try:
    series = cached_series(key)
except M.MarketDataError as e:
    st.error(f"No data for {spec.name}. {e}")
    st.caption(f"Source: {spec.source}. Try again later; nothing is cached for this series yet.")
    st.stop()

if series.status == "cached":
    st.warning(f"Live fetch failed. Showing the cached copy fetched "
               f"{series.fetched_at[:16].replace('T', ' ')} (as of {series.as_of:%d %b %Y}).")

# --- Indicators on full history, then slice (so long averages are valid at range start) -----
full = series.data
close = full["close"]
y = spec.is_yield
bands = I.bollinger(close, bb_window, bb_width)
ind = pd.DataFrame({
    "ma_fast": I.sma(close, A.MARKETS_MA_FAST), "ma_slow": I.sma(close, A.MARKETS_MA_SLOW),
    "rsi": I.rsi(close, A.MARKETS_RSI_WINDOW),
    "vol": I.realised_vol(close, y, A.MARKETS_VOL_WINDOW, A.MARKETS_TRADING_DAYS),
    "state": I.breaches(close, bands),
}).join(bands)
months = A.MARKETS_RANGES_MONTHS[rng]
start = full.index[0] if months is None else full.index[-1] - pd.DateOffset(months=months)
view, iv = full[full.index >= start], ind[ind.index >= start]
cv = view["close"]
dd = I.drawdown(cv, y)  # drawdown within the selected range

# --- Summary strip --------------------------------------------------------------------------
stats = I.summary_stats(close, bands, y, A.MARKETS_TRADING_DAYS)
range_dd = float(dd.min())
fmt_level = (lambda v: f"{v:,.3f}%") if y else (lambda v: f"{v:,.4f}" if v < 10 else f"{v:,.2f}")
chg = (lambda v: f"{v:+.1f} bp") if y else (lambda v: f"{v * 100:+.2f}%")
vol_txt = f"{stats['one_year_vol']:.0f} bp/yr" if y else f"{stats['one_year_vol'] * 100:.1f}%"
dd_txt = f"{range_dd:.0f} bp" if y else f"{range_dd * 100:.1f}%"
pb = stats["pct_b"]
where = "above upper band" if pb > 1 else "below lower band" if pb < 0 else "inside the bands"
cols = st.columns(6)
cols[0].metric(f"Last ({spec.unit})", fmt_level(stats["last"]))
cols[1].metric("Daily change", chg(stats["daily_change"]))
cols[2].metric("1Y change" if y else "1Y return", chg(stats["one_year_change"]))
cols[3].metric("1Y volatility", vol_txt)
cols[4].metric(f"Max drawdown ({rng})", dd_txt)
cols[5].metric("Position in bands (%b)", f"{pb * 100:.0f}%", where, delta_color="off",
               delta_arrow="off")
st.caption(series.stamp)
explain("summary strip", f"""
- **Last / daily change**: latest close and the change from the previous close
  ({'bp of yield' if y else 'simple return'}).
- **1Y {'change' if y else 'return'}**: against the last close on or before one year earlier.
- **1Y volatility**: standard deviation of daily {'bp changes' if y else 'log returns'} over the
  last year × √{A.MARKETS_TRADING_DAYS}.
- **Max drawdown**: worst fall from a running peak within the selected range
  ({'bp from the highest yield' if y else 'close / running max − 1'}).
- **%b**: (close − lower band) / (upper − lower), with bands of {bb_window} days ±
  {bb_width:g} standard deviations (population). 0% = lower band, 100% = upper band.
""")

# --- Chart stack ------------------------------------------------------------------------------
has_volume = "volume" in view and view["volume"].notna().any()
rows = ["price"] + (["volume"] if has_volume else []) + ["rsi", "vol", "dd"]
heights = {"price": 0.46, "volume": 0.1, "rsi": 0.14, "vol": 0.14, "dd": 0.14}
titles = {"price": f"{spec.name} ({spec.unit})", "volume": "Volume",
          "rsi": f"RSI({A.MARKETS_RSI_WINDOW})",
          "vol": f"Realised vol {A.MARKETS_VOL_WINDOW}d ({'bp/yr' if y else '%, annualised'})",
          "dd": f"Drawdown ({'bp from peak' if y else '%'})"}
fig = make_subplots(rows=len(rows), cols=1, shared_xaxes=True, vertical_spacing=0.035,
                    row_heights=[heights[r] for r in rows],
                    subplot_titles=[titles[r] for r in rows])
row = {r: i + 1 for i, r in enumerate(rows)}
UP, DOWN = MKT["up"], MKT["down"]  # green up, violet down (not red/green)

weekly = len(view) > A.MARKETS_CANDLE_MAX_BARS
# Long ranges: plot week-end values of the daily indicators (display only; maths stays daily)
pv = iv.resample("W-FRI").last() if weekly else iv
pc = cv.resample("W-FRI").last().dropna() if weekly else cv
pdd = dd.resample("W-FRI").min().dropna() if weekly else dd
if spec.has_ohlc:
    bars = view
    if weekly:
        bars = view.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min",
                                           "close": "last", "volume": "sum"}).dropna(
            subset=["close"])
    fig.add_trace(go.Candlestick(
        x=bars.index, open=bars["open"], high=bars["high"], low=bars["low"], close=bars["close"],
        name="Weekly OHLC" if weekly else "Daily OHLC",
        increasing={"line": {"color": UP, "width": 1}, "fillcolor": UP},
        decreasing={"line": {"color": DOWN, "width": 1}, "fillcolor": DOWN}),
        row=row["price"], col=1)
    if has_volume:
        up = (bars["close"] >= bars["open"]).to_numpy()
        fig.add_trace(go.Bar(x=bars.index, y=bars["volume"], name="Volume", showlegend=False,
                             marker_color=np.where(up, UP, DOWN), marker_line_width=0,
                             opacity=0.7), row=row["volume"], col=1)
else:
    fig.add_trace(go.Scatter(x=pc.index, y=pc, name="Close", mode="lines",
                               line={"color": ACCENT, "width": 1.5}), row=row["price"], col=1)

# Bollinger bands (shaded), middle line, moving averages
fig.add_trace(go.Scatter(x=pv.index, y=pv["upper"], name=f"Bollinger {bb_window}, ±{bb_width:g}σ",
                           mode="lines", line={"color": MKT["band"], "width": 1}),
              row=row["price"], col=1)
fig.add_trace(go.Scatter(x=pv.index, y=pv["lower"], name="Lower band", mode="lines",
                         showlegend=False, line={"color": MKT["band"], "width": 1},
                         fill="tonexty", fillcolor=MKT["band_fill"]),
              row=row["price"], col=1)
fig.add_trace(go.Scatter(x=pv.index, y=pv["mid"], name=f"Band middle (SMA {bb_window})",
                           mode="lines", line={"color": MKT["band"], "width": 1, "dash": "dot"}),
              row=row["price"], col=1)
fig.add_trace(go.Scatter(x=pv.index, y=pv["ma_fast"], name=f"MA {A.MARKETS_MA_FAST}",
                           mode="lines", line={"color": MKT["ma_fast"], "width": 1.5}),
              row=row["price"], col=1)
fig.add_trace(go.Scatter(x=pv.index, y=pv["ma_slow"], name=f"MA {A.MARKETS_MA_SLOW}",
                           mode="lines", line={"color": MKT["ma_slow"], "width": 1.5,
                                                "dash": "dash"}),
              row=row["price"], col=1)
# Breach markers: shape and colour both encode the side
for side, symbol, color, name in ((1, "triangle-down", MKT["above"], "Close above upper band"),
                                  (-1, "triangle-up", MKT["below"], "Close below lower band")):
    pts = cv[iv["state"] == side]
    fig.add_trace(go.Scatter(x=pts.index, y=pts, mode="markers", name=name,
                               marker={"symbol": symbol, "size": 8, "color": color,
                                       "line": {"color": MKT["marker_edge"], "width": 1}}),
                  row=row["price"], col=1)

fig.add_trace(go.Scatter(x=pv.index, y=pv["rsi"], name="RSI", mode="lines", showlegend=False,
                           line={"color": ACCENT, "width": 1.2}), row=row["rsi"], col=1)
for level in A.MARKETS_RSI_LEVELS:
    fig.add_hline(y=level, line={"color": MUTED, "dash": "dot", "width": 1}, row=row["rsi"],
                  col=1)
vol_y = pv["vol"] if y else pv["vol"] * 100
fig.add_trace(go.Scatter(x=pv.index, y=vol_y, name="Realised vol", mode="lines",
                           showlegend=False, line={"color": MKT["vol"], "width": 1.2}),
              row=row["vol"], col=1)
dd_y = pdd if y else pdd * 100
fig.add_trace(go.Scatter(x=pdd.index, y=dd_y, name="Drawdown", mode="lines", showlegend=False,
                         line={"color": MKT["dd"], "width": 1},
                         fill="tozeroy", fillcolor=MKT["dd_fill"]),
              row=row["dd"], col=1)

style(fig, f"{spec.name}: level, bands and risk ({rng})", height=980)
fig.update_layout(xaxis_rangeslider_visible=False, hovermode="x unified",
                  legend={"y": -0.06})
fig.update_yaxes(range=[0, 100], row=row["rsi"], col=1)
if log_axis and not y:
    fig.update_yaxes(type="log", row=row["price"], col=1)
if has_volume:
    fig.update_yaxes(tickformat="~s", row=row["volume"], col=1)
show(fig)
st.caption(series.stamp + (" · weekly bars and week-end indicator values shown for this range"
                           if weekly else ""))
explain("chart stack", f"""
- **Price**: {'candlesticks (weekly above ' + str(A.MARKETS_CANDLE_MAX_BARS) + ' daily bars)'
              if spec.has_ohlc else 'daily close (this series has no open/high/low)'}, with
  Bollinger bands ({bb_window} days, ±{bb_width:g} population standard deviations around the
  simple moving average) and {A.MARKETS_MA_FAST}/{A.MARKETS_MA_SLOW}-day simple moving averages.
  ▼ marks a close above the upper band, ▲ a close below the lower band.
- **RSI({A.MARKETS_RSI_WINDOW})**: Wilder's smoothing; guides at {A.MARKETS_RSI_LEVELS[0]} and
  {A.MARKETS_RSI_LEVELS[1]}.
- **Realised vol**: rolling {A.MARKETS_VOL_WINDOW}-day standard deviation of daily
  {'bp changes' if y else 'log returns'} × √{A.MARKETS_TRADING_DAYS}.
- **Drawdown**: from the running peak within the selected range.
Indicators are computed on the full history, then shown for the range, so long averages are
valid from the first day shown.
""")

# --- Bollinger breaches: frequency and what came next ----------------------------------------
st.subheader("Bollinger band breaches")
study = I.breach_study(cv, iv[["upper", "lower"]], A.MARKETS_FORWARD_DAYS, y)
h1, h2 = A.MARKETS_FORWARD_DAYS
scale = 1.0 if y else 100.0
unit = "bp" if y else "%"
table(pd.DataFrame({
    "Breach": study["side"],
    "Days outside (%)": study["days_outside_pct"],
    "Breach events": study["events"],
    f"Avg next {h1}d ({unit})": study[f"avg_next_{h1}d"] * scale,
    f"All days next {h1}d ({unit})": study[f"all_days_next_{h1}d"] * scale,
    f"Avg next {h2}d ({unit})": study[f"avg_next_{h2}d"] * scale,
    f"All days next {h2}d ({unit})": study[f"all_days_next_{h2}d"] * scale,
}), {"Days outside (%)": "pct", "Breach events": "int", f"Avg next {h1}d ({unit})": "num2",
     f"All days next {h1}d ({unit})": "num2", f"Avg next {h2}d ({unit})": "num2",
     f"All days next {h2}d ({unit})": "num2"})
st.markdown(
    "**Bands describe range, not direction.** A close outside the bands says the move was large "
    "relative to the recent spread of prices. It does not say what comes next: compare each "
    "average with the all-days average beside it, and note how few events some ranges contain.")
st.caption(series.stamp + f" · breaches counted within the selected range ({rng}); an event is "
           "the first close outside the band after being inside.")
explain("breach statistics", f"""
- **Days outside**: share of days in the range with a valid band whose close was above the upper
  (or below the lower) band.
- **Breach events**: first day outside after being inside or on the other side.
- **Avg next {h1}d / {h2}d**: mean {'bp change in yield' if y else 'simple return'} from the
  event close to the close {h1} and {h2} trading days later; events without that much future data
  are excluded. **All days** is the same average over every day in the range, for comparison.
""")
