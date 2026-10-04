"""Markets: daily history with a trader-style indicator stack. Display analytics only; nothing
here feeds the financing engine."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import assumptions as A
from analytics import indicators as I
from analytics import market_stats as MS
from data import markets as M
from ui.common import (ACCENT, CHART_TEXT_PX, DIVERGING, MKT, MUTED, TABLE_ROW_PX, explain, show,
                       style, table)

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
cols[0].metric("Last", fmt_level(stats["last"]))
cols[1].metric("Daily change", chg(stats["daily_change"]))
cols[2].metric("1Y change" if y else "1Y return", chg(stats["one_year_change"]))
cols[3].metric("1Y volatility", vol_txt)
cols[4].metric("Max drawdown", dd_txt)
cols[5].metric("Band position", f"{pb * 100:.0f}%", where, delta_color="off",
               delta_arrow="off")
st.caption(f"Last in {spec.unit}. Max drawdown over the selected range ({rng}). Band position is "
           "%b: 0% = lower band, 100% = upper band.")
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
        increasing={"line": {"color": UP, "width": 1.3}, "fillcolor": UP},
        decreasing={"line": {"color": DOWN, "width": 1.3}, "fillcolor": DOWN}),
        row=row["price"], col=1)
    if has_volume:
        up = (bars["close"] >= bars["open"]).to_numpy()
        fig.add_trace(go.Bar(x=bars.index, y=bars["volume"], name="Volume", showlegend=False,
                             marker_color=np.where(up, UP, DOWN), marker_line_width=0,
                             opacity=0.7), row=row["volume"], col=1)
else:
    fig.add_trace(go.Scatter(x=pc.index, y=pc, name="Close", mode="lines",
                               line={"color": ACCENT, "width": 2.5}), row=row["price"], col=1)

# Bollinger bands (shaded), middle line, moving averages
fig.add_trace(go.Scatter(x=pv.index, y=pv["upper"], name=f"Bollinger {bb_window}, ±{bb_width:g}σ",
                           mode="lines", line={"color": MKT["band"], "width": 1.8}),
              row=row["price"], col=1)
fig.add_trace(go.Scatter(x=pv.index, y=pv["lower"], name="Lower band", mode="lines",
                         showlegend=False, line={"color": MKT["band"], "width": 1.8},
                         fill="tonexty", fillcolor=MKT["band_fill"]),
              row=row["price"], col=1)
fig.add_trace(go.Scatter(x=pv.index, y=pv["mid"], name=f"Band middle (SMA {bb_window})",
                           mode="lines", line={"color": MKT["band"], "width": 1.5, "dash": "dot"}),
              row=row["price"], col=1)
fig.add_trace(go.Scatter(x=pv.index, y=pv["ma_fast"], name=f"MA {A.MARKETS_MA_FAST}",
                           mode="lines", line={"color": MKT["ma_fast"], "width": 2.5}),
              row=row["price"], col=1)
fig.add_trace(go.Scatter(x=pv.index, y=pv["ma_slow"], name=f"MA {A.MARKETS_MA_SLOW}",
                           mode="lines", line={"color": MKT["ma_slow"], "width": 2.5,
                                                "dash": "dash"}),
              row=row["price"], col=1)
# Breach markers: shape and colour both encode the side
for side, symbol, color, name in ((1, "triangle-down", MKT["above"], "Close above upper band"),
                                  (-1, "triangle-up", MKT["below"], "Close below lower band")):
    pts = cv[iv["state"] == side]
    fig.add_trace(go.Scatter(x=pts.index, y=pts, mode="markers", name=name,
                               marker={"symbol": symbol, "size": 10, "color": color,
                                       "line": {"color": MKT["marker_edge"], "width": 1}}),
                  row=row["price"], col=1)

fig.add_trace(go.Scatter(x=pv.index, y=pv["rsi"], name="RSI", mode="lines", showlegend=False,
                           line={"color": ACCENT, "width": 2}), row=row["rsi"], col=1)
for level in A.MARKETS_RSI_LEVELS:
    fig.add_hline(y=level, line={"color": MUTED, "dash": "dot", "width": 1.5}, row=row["rsi"],
                  col=1)
vol_y = pv["vol"] if y else pv["vol"] * 100
fig.add_trace(go.Scatter(x=pv.index, y=vol_y, name="Realised vol", mode="lines",
                           showlegend=False, line={"color": MKT["vol"], "width": 2}),
              row=row["vol"], col=1)
dd_y = pdd if y else pdd * 100
fig.add_trace(go.Scatter(x=pdd.index, y=dd_y, name="Drawdown", mode="lines", showlegend=False,
                         line={"color": MKT["dd"], "width": 2},
                         fill="tozeroy", fillcolor=MKT["dd_fill"]),
              row=row["dd"], col=1)

style(fig, f"{spec.name}: level, bands and risk ({rng})", height=1120,
      subtitle=f"{'Weekly bars (indicators computed daily)' if weekly else 'Daily'} · "
               f"{spec.source} · as of {series.as_of:%d %b %Y}")
fig.update_layout(xaxis_rangeslider_visible=False, hovermode="x unified")
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

# =============================================================================================
# Cross-asset and distribution analytics (descriptive only; nothing here is a forecast)
# =============================================================================================


def sub(sources: str, as_of) -> str:
    return f"Daily · {sources} · as of {as_of:%d %b %Y}"


def pct_changes(close_: pd.Series, is_y: bool) -> pd.Series:
    """Daily changes in display units: bp for yields, % log return for prices."""
    return I.changes(close_, is_y) * (1.0 if is_y else 100.0)


def change_unit(is_y: bool) -> str:
    return "bp" if is_y else "% log return"


# --- Cross-asset correlation matrix ----------------------------------------------------------
st.subheader("Cross-asset correlation")
loaded, missing = {}, []
for k in M.SERIES:
    try:
        loaded[k] = cached_series(k)
    except M.MarketDataError as e:
        missing.append(f"{M.SERIES[k].name} ({e})")
if missing:
    st.warning("Left out of the cross-asset sections (no live data and no cached copy): "
               + "; ".join(missing))
closes = {k: s.data["close"] for k, s in loaded.items()}
isy = {k: M.SERIES[k].is_yield for k in loaded}
names = {k: M.SERIES[k].name for k in loaded}
x_asof = min(s.as_of for s in loaded.values())
x_src = "Yahoo Finance (not an official provider), EIA, BoE, Bundesbank"
cw_opts = list(A.MARKETS_CORR_WINDOWS)
cw = st.radio("Correlation window (most recent common trading days)", cw_opts,
              index=cw_opts.index(A.MARKETS_CORR_DEFAULT), horizontal=True, key="mkt_corr_win")
if len(loaded) >= 2:
    corr, nobs = MS.corr_matrix(closes, isy, A.MARKETS_CORR_WINDOWS[cw], A.MARKETS_MIN_OBS)
    labels = [names[k] for k in corr.index]
    text = [[("n/a" if np.isnan(corr.iloc[i, j]) else f"{corr.iloc[i, j]:+.2f}")
             for j in range(len(corr))] for i in range(len(corr))]
    fig = go.Figure(go.Heatmap(
        z=corr.to_numpy(), x=labels, y=labels, zmin=-1, zmax=1, colorscale=DIVERGING,
        text=text, texttemplate="%{text}", textfont={"size": CHART_TEXT_PX},
        customdata=nobs.to_numpy(), colorbar={"title": {"text": "corr"}},
        hovertemplate="%{y} vs %{x}<br>correlation %{z:+.2f}<br>%{customdata} common days"
                      "<extra></extra>"))
    style(fig, f"Correlation of daily changes, last {cw}", height=560,
          subtitle=sub(x_src, x_asof))
    fig.update_yaxes(autorange="reversed")
    show(fig)
    st.caption(f"Pearson correlation of daily changes (log returns for prices, bp changes for "
               f"yields) on dates where both series have a close. A pair needs at least "
               f"{A.MARKETS_MIN_OBS} common days. A rising yield is a falling bond price, so a "
               "negative equity-yield correlation means bonds and equities rose together. "
               f"Hover for the number of common days. As of {x_asof:%d %b %Y} (earliest last "
               "date across the series).")
else:
    st.info("Correlation needs at least two series with data.")

# --- Rolling correlation and beta ------------------------------------------------------------
st.subheader("Rolling correlation and beta for a pair")
keys = list(loaded)
if len(keys) >= 2:
    p1, p2, p3 = st.columns([3, 3, 2])
    ka = p1.selectbox("Series A", keys, index=0, format_func=names.get, key="mkt_pair_a")
    kb = p2.selectbox("Series B (beta is A on B)", [k for k in keys if k != ka], index=0,
                      format_func=names.get, key="mkt_pair_b")
    rw = p3.selectbox("Window (days)", A.MARKETS_ROLL_WINDOWS,
                      index=A.MARKETS_ROLL_WINDOWS.index(A.MARKETS_ROLL_DEFAULT), key="mkt_roll")
    joined = pd.concat({ka: closes[ka], kb: closes[kb]}, axis=1, join="inner").dropna()
    cha, chb = pct_changes(joined[ka], isy[ka]), pct_changes(joined[kb], isy[kb])
    rc = MS.rolling_corr_beta(cha, chb, rw)
    rc = rc[rc.index >= start].dropna()
    if len(rc) >= 2:
        beta_unit = f"{change_unit(isy[ka])} of A per 1 {change_unit(isy[kb])} of B"
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                            subplot_titles=[f"Rolling {rw}-day correlation",
                                            f"Rolling {rw}-day beta ({beta_unit})"])
        fig.add_trace(go.Scatter(x=rc.index, y=rc["corr"], mode="lines", name="Correlation",
                                 line={"color": ACCENT, "width": 2.5},
                                 hovertemplate="%{x|%d %b %Y}<br>corr %{y:+.2f}<extra></extra>"),
                      row=1, col=1)
        fig.add_trace(go.Scatter(x=rc.index, y=rc["beta"], mode="lines", name="Beta",
                                 line={"color": MKT["ma_fast"], "width": 2.5, "dash": "dash"},
                                 hovertemplate="%{x|%d %b %Y}<br>beta %{y:+.3f}<extra></extra>"),
                      row=2, col=1)
        for r_ in (1, 2):
            fig.add_hline(y=0, line={"color": MUTED, "width": 1, "dash": "dot"}, row=r_, col=1)
        fig.update_yaxes(range=[-1, 1], row=1, col=1)
        pair_src = "; ".join(dict.fromkeys(M.SERIES[k].source for k in (ka, kb)))
        style(fig, f"{names[ka]} vs {names[kb]}: rolling correlation and beta ({rng})",
              height=640, subtitle=sub(pair_src, joined.index[-1]))
        fig.update_layout(margin={"t": 118})  # room for the first subplot title under the subtitle
        show(fig)
        last = rc.iloc[-1]
        st.caption(f"Latest ({rc.index[-1]:%d %b %Y}): correlation {last['corr']:+.2f}, beta "
                   f"{last['beta']:+.3f} {beta_unit}. Beta = cov(A, B) / var(B) over the last "
                   f"{rw} common trading days; {len(joined):,} common days in total.")
    else:
        st.info(f"Not enough common data for a {rw}-day window in the selected range.")

# --- Volatility regimes -----------------------------------------------------------------------
st.subheader(f"Volatility regimes: {spec.name}")
lo_p, hi_p = A.MARKETS_REGIME_PCTS
labels_all, lo_v, hi_v = MS.regimes(ind["vol"], lo_p, hi_p)
lab_view = labels_all[labels_all.index >= start]
ch_full = pct_changes(close, y)
reg = MS.regime_table(lab_view, ch_full)
REG_FILL = {"low": "rgba(109,211,255,0.16)", "high": "rgba(215,126,232,0.22)"}
REG_KEY = {"low": "rgba(109,211,255,0.7)", "high": "rgba(215,126,232,0.7)"}
fig = go.Figure()
fig.add_trace(go.Scatter(x=pc.index, y=pc, name="Close", mode="lines",
                         line={"color": ACCENT, "width": 2.2},
                         hovertemplate="%{x|%d %b %Y}<br>%{y:,.2f}<extra></extra>"))
lab_plot = lab_view.resample("W-FRI").last().dropna() if weekly else lab_view
step = pd.Timedelta(days=7 if weekly else 1)
for a_, b_, r_ in MS.runs(lab_plot):
    if r_ in REG_FILL:
        fig.add_vrect(x0=a_, x1=b_ + step, fillcolor=REG_FILL[r_], line_width=0, layer="below")
for r_, nm in (("low", f"Low vol (below {lo_p}th pct)"), ("high", f"High vol (above {hi_p}th pct)")):
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=nm,
                             marker={"symbol": "square", "size": 14, "color": REG_KEY[r_]}))
style(fig, f"{spec.name} with volatility regimes shaded ({rng}), {spec.unit}", y_title=spec.unit,
      height=480, subtitle=sub(spec.source, series.as_of))
if log_axis and not y:
    fig.update_yaxes(type="log")
show(fig)
vu = "bp/yr" if y else "% annualised"
vs = 1.0 if y else 100.0
st.caption(f"Regime = rolling {A.MARKETS_VOL_WINDOW}-day realised volatility against its own "
           f"full history ({labels_all.index[0]:%b %Y} to {labels_all.index[-1]:%b %Y}): low below "
           f"{lo_v * vs:.1f} {vu} ({lo_p}th percentile), high above {hi_v * vs:.1f} {vu} "
           f"({hi_p}th percentile), normal between. Unshaded = normal. The thresholds use the "
           "whole history, so they are descriptive, not something known in real time.")
cu = "bp" if y else "%"
table(pd.DataFrame({"Regime": reg["regime"], "Days": reg["days"], "Time in regime (%)": reg["share"],
                    f"Mean daily change ({cu})": reg["mean"], f"SD daily change ({cu})": reg["sd"]}),
      {"Days": "int", "Time in regime (%)": "pct", f"Mean daily change ({cu})": "num2",
       f"SD daily change ({cu})": "num2"})
st.caption(f"Within the selected range ({rng}). Mean and SD are of same-day daily changes "
           f"({change_unit(y)}); the day's own change is part of the volatility that defines its "
           "regime, so this describes the regime, it does not predict the next day.")

# --- Return distribution ------------------------------------------------------------------------
st.subheader(f"Daily change distribution: {spec.name}")
chv = ch_full[ch_full.index >= start].dropna()
if len(chv) >= A.MARKETS_MIN_OBS:
    mu, sd = float(chv.mean()), float(chv.std(ddof=1))
    xs = np.linspace(float(chv.min()), float(chv.max()), 300)
    pdf = np.exp(-0.5 * ((xs - mu) / sd) ** 2) / (sd * np.sqrt(2 * np.pi))
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=chv, nbinsx=A.MARKETS_HIST_BINS, histnorm="probability density",
                               name="Observed", marker_color=MKT["band"], opacity=0.75,
                               hovertemplate="%{x}<br>density %{y:.3f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=xs, y=pdf, mode="lines", name="Normal, same mean and SD",
                             line={"color": MKT["ma_fast"], "width": 2.5, "dash": "dash"}))
    style(fig, f"{spec.name}: distribution of daily changes ({rng}), {change_unit(y)}",
          x_title=f"Daily change ({change_unit(y)})", y_title="Density", height=460,
          subtitle=sub(spec.source, series.as_of))
    show(fig)
    tl = MS.tails(chv, A.MARKETS_TAIL_PCTS)
    tc = MS.tail_counts(chv)
    table(pd.DataFrame({"Percentile": tl["percentile"], f"Empirical ({cu})": tl["empirical"],
                        f"Normal ({cu})": tl["normal"],
                        f"Empirical − normal ({cu})": tl["empirical"] - tl["normal"]}),
          {"Percentile": "int", f"Empirical ({cu})": "num2", f"Normal ({cu})": "num2",
           f"Empirical − normal ({cu})": "num2"})
    st.caption(f"{tc['n']:,} daily changes in the range. Beyond 3 SD of the mean: "
               f"{tc['observed']} observed against {tc['expected']:.1f} for a normal. Skew "
               f"{tc['skew']:+.2f}, excess kurtosis {tc['excess_kurtosis']:+.2f} (0 for a "
               "normal). Empirical percentiles use linear interpolation.")
else:
    st.info(f"Fewer than {A.MARKETS_MIN_OBS} daily changes in the selected range.")

# --- Seasonality by month -------------------------------------------------------------------------
st.subheader(f"Seasonality by calendar month: {spec.name}")
mch = MS.monthly_changes(close, y)
if len(mch) >= 12:
    sea = MS.seasonality(mch, A.MARKETS_SEASON_MIN_N)
    mnames = [pd.Timestamp(2000, m, 1).strftime("%b") for m in sea.index]
    small = sea["small_sample"].to_numpy()
    fig = go.Figure(go.Bar(
        x=mnames, y=sea["mean"], name="Mean monthly change",
        marker={"color": np.where(sea["mean"] >= 0, MKT["up"], MKT["down"]).tolist(),
                "pattern": {"shape": np.where(small, "/", "").tolist()}},
        text=[f"n={n}" for n in sea["n"]], textposition="outside",
        textfont={"size": CHART_TEXT_PX},
        hovertemplate="%{x}<br>mean %{y:+.2f}<br>%{text}<extra></extra>"))
    fig.add_hline(y=0, line={"color": MUTED, "width": 1})
    style(fig, f"{spec.name}: mean change by calendar month, {cu}", y_title=cu, height=460,
          subtitle=f"Monthly (month-end to month-end) · {spec.source} · "
                   f"{mch.index[0]:%b %Y} to {mch.index[-1]:%b %Y}")
    show(fig)
    table(pd.DataFrame({"Month": mnames, f"Mean ({cu})": sea["mean"].to_numpy(),
                        f"Median ({cu})": sea["median"].to_numpy(), f"SD ({cu})": sea["sd"].to_numpy(),
                        "Up months (%)": sea["pct_up"].to_numpy(), "Months (n)": sea["n"].to_numpy(),
                        "Small sample": np.where(small, "yes", "")}),
          {f"Mean ({cu})": "num2", f"Median ({cu})": "num2", f"SD ({cu})": "num2",
           "Up months (%)": "pct", "Months (n)": "int"}, height=13 * TABLE_ROW_PX + 3)
    st.caption(f"Full history, complete months only ({len(mch):,} months, "
               f"{mch.index[0]:%b %Y} to {mch.index[-1]:%b %Y}); the current month is excluded. "
               f"Hatched bars have fewer than {A.MARKETS_SEASON_MIN_N} observations. Small "
               "samples: each calendar month has one observation per year, so a few unusual years "
               "can set the average. Compare each mean with its SD before reading anything into it.")
else:
    st.info("Fewer than 12 complete months of data: no seasonality shown.")
