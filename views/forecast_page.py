"""Forecast Lab (EXPERIMENTAL): displays the saved results of the offline walk-forward test in
scripts/run_forecasts.py. This page never fits, trains or refits anything; it only reads
data/forecasts/. Every sentence is generated from the saved numbers."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import assumptions as A
from data import forecast_store as FS
from ui.common import TABLE_ROW_PX, explain, show, style, table
from ui.series_chart import LINE_COLORS, LINE_DASHES, NEWLINE

LABEL = "EXPERIMENTAL"
# Loss differences shown in readable units: metric -> (multiplier, unit)
DISPLAY = {"QLIKE": (1.0, "QLIKE units"),
           "MAE of volatility": (100.0, "pp of 10-day vol"),
           "Squared error": (1e8, "bp²"),
           "0-1 loss (wrong calls)": (100.0, "pp of calls")}
VOL_NAMES = {"realised": "Realised (next 10 days)", "naive": "Naive (last 10 days)",
             "ewma": "EWMA", "garch": "GARCH(1,1)"}
RULE_NAMES = {"buy_and_hold": "Buy and hold", "drift": "Drift (long if > 0)",
              "ridge": "Ridge (long if > 0)", "logistic": "Logistic (long if p > 0.5)"}
RANGES = {"1Y": 12, "5Y": 60, "10Y": 120, "Max": None}

st.warning(f"**{LABEL}.** A one-off historical walk-forward test of simple, pre-declared models. "
           "It reports how they compared with a naive baseline on past data. It is not a "
           "forecasting service, makes no claim about future results, and nothing here feeds the "
           "financing engine.")

try:
    summary = FS.load_summary()
except FS.ForecastStoreError as e:
    st.error(f"Forecast Lab results are not available: {e}")
    st.markdown("Run the offline script, then reload this page:" + NEWLINE + NEWLINE +
                "```" + NEWLINE + r".venv\Scripts\python scripts\run_forecasts.py" + NEWLINE + "```")
    st.stop()

results = pd.DataFrame(summary["results"])
series = {m["name"]: m for m in summary["series"]}
st.caption(f"Results computed offline on {summary['run_at'].replace('T', ' ')} by "
           "scripts/run_forecasts.py; this page only reads them. GARCH: "
           + (f"arch {summary['arch_version']}." if summary.get("arch_version") else
              "not run (the arch package was not installed)."))
for f in summary.get("failures", []):
    st.error(f"Not run: {f}")
for m in series.values():
    if m["status"] == "cached":
        st.warning(f"{m['name']}: the run used the cached copy fetched "
                   f"{m['fetched_at'][:16].replace('T', ' ')} (live fetch failed).")

st.subheader("Headline (generated from the results)")
st.markdown(summary["headline"])
if results.empty:
    st.stop()

# --- Verdict table ---------------------------------------------------------------------------
st.subheader("Model versus naive, by target")
pick = st.selectbox("Series", list(series), key="fl_series")
meta = series[pick]
sub = results[results["series"] == pick]
rows = []
for r in sub.to_dict("records"):
    mult, unit = DISPLAY[r["metric"]]
    # verdict next to the model so it is visible at laptop width; unit and obs last
    rows.append({"Target": r["target"], "Model": r["model"], "Metric": r["metric"],
                 "Verdict": r["verdict"] + ("*" if r.get("note") else ""),
                 "Diff vs naive": r["diff_mean"] * mult,
                 f"{A.FORECAST_CONFIDENCE:.0%} low": r["ci_lo"] * mult,
                 f"{A.FORECAST_CONFIDENCE:.0%} high": r["ci_hi"] * mult, "Unit": unit,
                 "Obs": r["n"]})
table(pd.DataFrame(rows), {"Obs": "int", "Diff vs naive": "num2",
                           f"{A.FORECAST_CONFIDENCE:.0%} low": "num2",
                           f"{A.FORECAST_CONFIDENCE:.0%} high": "num2"},
      height=(len(rows) + 1) * TABLE_ROW_PX + 3)  # every row visible, no inner scroll
counts = sub["verdict"].value_counts()
st.markdown(f"For {pick}: {counts.get('beats naive', 0)} of {len(sub)} comparisons \"beats naive\", "
            f"{counts.get('does not beat naive', 0)} \"does not beat naive\", "
            f"{counts.get('inconclusive', 0)} \"inconclusive\".")
st.caption((r"\* Same calls as naive on every test date (the drift was positive throughout), "
            "so there is nothing to compare. " if sub["note"].astype(bool).any() else "")
           + f"Diff = mean of (model loss − naive loss) over the test dates; negative means lower "
           f"loss than naive. Interval: moving-block bootstrap ({A.FORECAST_BOOT_BLOCK}-day blocks, "
           f"{A.FORECAST_BOOT_N:,} replicates). Verdict: \"beats naive\" if the whole interval is "
           "below 0, \"does not beat naive\" if it is wholly above 0, otherwise inconclusive. "
           f"Source: {meta['source']}, daily closes {meta['sample_start']} to {meta['sample_end']} "
           f"({meta['status']}, as of {meta['as_of']}).")
hr = pd.DataFrame(meta["hit_rates"])
if not hr.empty:
    hr = hr.rename(columns={"target": "Target", "model": "Model", "n": "Obs",
                            "hit_rate": "Hit rate", "share_long": "Share of up calls"})
    hr[["Hit rate", "Share of up calls"]] *= 100
    table(hr.drop(columns="series"), {"Obs": "int", "Hit rate": "pct", "Share of up calls": "pct"})

# --- Volatility chart -----------------------------------------------------------------------------
st.subheader("Next-10-day volatility: forecasts against what followed")
rng = st.radio("Range", list(RANGES), index=1, horizontal=True, key="fl_range")
try:
    vol = FS.load_frame(f"{meta['key']}_vol")
except FS.ForecastStoreError as e:
    st.error(str(e))
    vol = None
if vol is not None:
    if RANGES[rng] is not None:
        vol = vol[vol.index >= vol.index[-1] - pd.DateOffset(months=RANGES[rng])]
    h = A.FORECAST_VOL_HORIZON
    ann = np.sqrt(vol * A.FORECAST_TRADING_DAYS / h) * 100  # h-day variance -> annualised vol, %
    fig = go.Figure()
    for i, col in enumerate(c for c in VOL_NAMES if c in ann):
        fig.add_scatter(x=ann.index, y=ann[col], name=VOL_NAMES[col], mode="lines",
                        line={"color": LINE_COLORS[i], "width": 2.5 if i == 0 else 1.8,
                              "dash": LINE_DASHES[i]},
                        hovertemplate="%{x|%d %b %Y}<br>%{y:.1f}%<extra>" + VOL_NAMES[col] + "</extra>")
    style(fig, f"{pick}: next-10-day volatility, realised vs forecast, annualised %",
          y_title="annualised volatility, %", height=480,
          subtitle=f"{LABEL} · Daily · {meta['source']} · test dates {meta['vol_test_start']} to "
                   f"{meta['vol_test_end']}")
    show(fig)
    st.caption("Each forecast is dated the day it was made and uses closes up to that day only; "
               "the realised line is the volatility of the following 10 trading days. "
               f"Annualised with √({A.FORECAST_TRADING_DAYS}/{h}).")

# --- Equity curves -----------------------------------------------------------------------------
st.subheader("Next-day rules: equity curve net of costs against buy and hold")
try:
    eq = FS.load_frame(f"{meta['key']}_equity")
except FS.ForecastStoreError as e:
    st.error(str(e))
    eq = None
if eq is not None:
    fig = go.Figure()
    for i, col in enumerate(c for c in RULE_NAMES if c in eq):
        fig.add_scatter(x=eq.index, y=eq[col], name=RULE_NAMES[col], mode="lines",
                        line={"color": LINE_COLORS[i], "width": 2.2, "dash": LINE_DASHES[i]},
                        hovertemplate="%{x|%d %b %Y}<br>%{y:.2f}x<extra>" + RULE_NAMES[col]
                        + "</extra>")
    style(fig, f"{pick}: growth of 1, long or flat, net of {A.FORECAST_COST_BP:g} bp per trade "
               "(log scale)", y_title="growth of 1 (log scale)", height=480,
          subtitle=f"{LABEL} · Daily · {meta['source']} · {meta['return_test_start']} to "
                   f"{meta['return_test_end']}")
    fig.update_yaxes(type="log")
    show(fig)
    es = pd.DataFrame(meta["equity_stats"]).drop(columns="series")
    es["rule"] = es["rule"].map(RULE_NAMES)
    for c in ("total_return", "annual_return", "annual_vol", "max_drawdown", "share_long"):
        es[c] *= 100
    es = es.rename(columns={"rule": "Rule", "trades": "Trades", "share_long": "Days long",
                            "total_return": "Total return", "annual_return": "Annual return",
                            "annual_vol": "Annual vol", "max_drawdown": "Max drawdown"})
    table(es, {"Trades": "int", "Days long": "pct", "Total return": "pct",
               "Annual return": "pct", "Annual vol": "pct", "Max drawdown": "pct"})
    best = es.loc[es["Total return"].idxmax(), "Rule"]
    st.markdown(f"Over {meta['return_test_start']} to {meta['return_test_end']}, the highest "
                f"total return net of costs on this one historical path was {best}. One path has "
                "no confidence interval here; it is not evidence that the ordering repeats.")
    st.caption("Simplifications: the price index only (no dividends"
               + ("" if meta["provider"] == "yahoo" else ", no interest carry")
               + "); cash earns nothing while flat; one position per day decided at the close "
               f"and held to the next close; {A.FORECAST_COST_BP:g} bp of capital per position "
               "change (own assumption); no slippage, borrowing or tax.")

explain("the Forecast Lab method", f"""
- **Data:** daily closes from {A.FORECAST_SAMPLE_START} ({', '.join(series)}); returns are daily log
  returns. FTSE 100 and S&P 500 come from Yahoo Finance (not an official provider); GBP/USD from the
  Bank of England.
- **Walk-forward:** first forecast after {A.FORECAST_MIN_TRAIN_DAYS:,} days; expanding window;
  drift, ridge and logistic refitted every {A.FORECAST_REFIT_DAYS} days, GARCH every
  {A.FORECAST_GARCH_REFIT_DAYS}. A training row is used only once its whole target is observed
  (no look-ahead; asserted in the script and tested).
- **Volatility:** naive = last {A.FORECAST_VOL_HORIZON} days' realised variance; EWMA λ
  {A.FORECAST_EWMA_LAMBDA}; GARCH(1,1), zero mean, normal errors. Losses: QLIKE (ln F + RV/F) and
  MAE of volatility.
- **Returns and direction:** naive = zero return / always up; drift = mean of past targets; ridge
  (α {A.FORECAST_RIDGE_ALPHA:g}) and logistic (L2 {A.FORECAST_LOGIT_L2:g}) on {A.FORECAST_LAGS}
  lagged returns, the 5-day return, {A.FORECAST_VOL_WINDOW}-day realised vol and EWMA vol, all
  standardised on the training window. Settings were fixed before the first run; none were tuned.
- **Verdicts** come from the bootstrap interval only; the headline counts them.
""")
