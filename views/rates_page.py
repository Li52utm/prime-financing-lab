"""Rates & Liquidity: curve slopes, sovereign spreads, liquidity, BoE balance sheet, SONIA
versus Bank Rate. Official public sources only; every chart states units, frequency, source and
as-of. Display analytics only: none of this feeds the financing engine."""

import pandas as pd
import streamlit as st

from analytics import series_stats as S
from data import events as EV
from ui.common import explain
from ui.macro_loader import get
from ui.series_chart import BAND_MODES, section

st.caption("Official central bank and treasury data for context. Statistics describe the data "
           "shown; none of this is a forecast or an input to the financing engine.")


RANGES = {"1Y": 12, "5Y": 60, "10Y": 120, "Max": None}
c1, c2, c3 = st.columns([3, 3, 2])
rng = c1.radio("Range", list(RANGES), index=1, horizontal=True, key="rl_range")
band_mode = c2.selectbox("Bands (over the selected range)", BAND_MODES, index=0, key="rl_bands")
show_ev = c3.toggle("Shade dated events", value=True, key="rl_events")
start = None if RANGES[rng] is None else pd.Timestamp.today().normalize() - pd.DateOffset(
    months=RANGES[rng])
st.caption(f"Statistics are computed over the selected range ({rng}). Changes are "
           "observation-to-observation at each series' own frequency.")


def ev(*regions):
    return EV.verified_events(regions) if show_ev else []


PROVIDER_LABEL = {"ecb": "ECB Data Portal", "boe": "Bank of England Database",
                  "bundesbank": "Deutsche Bundesbank", "ustreasury": "US Treasury",
                  "markets": "EIA / Bank of England"}


def src(series_by_key: dict) -> str:
    seen = []
    for s in series_by_key.values():
        label = PROVIDER_LABEL[s.spec.provider]
        if label not in seen:
            seen.append(label)
    return ", ".join(seen)


def asof(series_by_key: dict) -> str:
    days = sorted({s.as_of for s in series_by_key.values()})
    if not days:
        return ""
    return f"{days[0]:%d %b %Y}" if len(days) == 1 else f"{days[0]:%d %b %Y} to {days[-1]:%d %b %Y}"


def stamp_lines(series_by_key: dict) -> list[str]:
    return [f"{s.spec.name}: {s.stamp}" for s in series_by_key.values()]


def warn_status(series_by_key: dict):
    for s in series_by_key.values():
        if s.status == "cached":
            st.warning(f"{s.spec.name}: live fetch failed; showing the cached copy fetched "
                       f"{s.fetched_at[:16].replace('T', ' ')}.")


# --- 1. 2s10s slopes -----------------------------------------------------------------------
st.subheader("Curve slopes: 2s10s (10y minus 2y)")
d, errs = get(["us_2y", "us_10y", "ea_aaa_2y", "ea_aaa_10y", "de_2y", "de_10y"])
for e in errs:
    st.error(e)
lines = []
for label, a, b in (("US Treasury", "us_10y", "us_2y"), ("Euro area AAA", "ea_aaa_10y", "ea_aaa_2y"),
                    ("Germany (Bund)", "de_10y", "de_2y")):
    if a in d and b in d:
        lines.append((label, S.window(S.combine(d[a].data, d[b].data, 100), start)))
if lines:
    warn_status(d)
    section("2s10s slope (10y minus 2y), bp, daily", "bp", "daily", lines, stamp_lines(d),
            band_mode, ev("US", "EA"),
            note="Computed only on dates where both yields are published (no filling). UK, France "
                 "and Italy 2s10s are not shown: no free official daily or monthly 2y series was "
                 "found for them (BoE publishes 5y, 10y and 20y par yields, not 2y).",
            sources=src(d), as_of=asof(d))
explain("2s10s slope", """
Slope = 10-year yield − 2-year yield, in basis points, on days both are published.
US: Treasury par yields. Euro area: ECB AAA-rated government Svensson spot rates. Germany:
Bundesbank Svensson yields on Federal securities. A negative slope means the curve is inverted.
""")

# --- 2. Sovereign spreads (monthly) --------------------------------------------------------
st.subheader("Sovereign 10y spreads to Germany (monthly)")
d, errs = get(["de_10y_m", "fr_10y_m", "it_10y_m"])
for e in errs:
    st.error(e)
lines = [(lbl, S.window(S.combine(d[a].data, d["de_10y_m"].data, 100), start))
         for lbl, a in (("France minus Germany", "fr_10y_m"), ("Italy minus Germany", "it_10y_m"))
         if a in d and "de_10y_m" in d]
if lines:
    warn_status(d)
    section("10y spread to Germany, bp, MONTHLY", "bp", "monthly", lines, stamp_lines(d),
            band_mode, ev("EA"),
            note="MONTHLY data: ECB long-term interest rates for convergence purposes (monthly "
                 "averages, dated to the 1st of the month). No free official daily French or "
                 "Italian 10y series was found, so these spreads are monthly.",
            sources=src(d), as_of=asof(d))

# --- 3. Euro liquidity ---------------------------------------------------------------------
st.subheader("Euro area liquidity (Eurosystem)")
d, errs = get(["ecb_exliq", "ecb_df", "ecb_ca", "ecb_mlf"])
for e in errs:
    st.error(e)
if "ecb_exliq" in d:
    warn_status({"ecb_exliq": d["ecb_exliq"]})
    section("Excess liquidity (official ECB series), EUR bn, daily", "EUR bn", "daily",
            [("Excess liquidity", S.window(d["ecb_exliq"].data / 1000, start))],
            [d["ecb_exliq"].stamp], band_mode, ev("EA"),
            note="The ECB publishes this daily series only from 27 Sep 2024, so its history and "
                 "statistics are short. ECB definition: current accounts − minimum reserve "
                 "requirements + deposit facility − marginal lending facility.",
            sources=src(d), as_of=asof(d))
if all(k in d for k in ("ecb_df", "ecb_ca", "ecb_mlf")):
    held = d["ecb_df"].data + d["ecb_ca"].data
    held = (pd.concat({"h": held, "m": d["ecb_mlf"].data}, axis=1, join="inner").dropna()
            .pipe(lambda x: x["h"] - x["m"])) / 1000
    section("Liquidity held at the Eurosystem (DF + CA − MLF), EUR bn, daily", "EUR bn", "daily",
            [("DF + CA − MLF", S.window(held, start))],
            [f"{d[k].spec.name}: {d[k].stamp}" for k in ("ecb_df", "ecb_ca", "ecb_mlf")],
            band_mode, ev("EA"),
            note="NOT the official excess liquidity measure: reserve requirements are not deducted "
                 "because no reserve-requirement series exists before Sep 2024. On the 358 days where "
                 "both exist, the ECB's official excess liquidity equals this minus requirements "
                 "(checked on 2026-10-04, median difference EUR 0.3m).",
            sources=src(d), as_of=asof(d))

# --- 4. BoE reserves vs APF -------------------------------------------------------------------
st.subheader("Bank of England reserves and APF gilt holdings (weekly)")
d, errs = get(["boe_reserves", "boe_apf_gilts"])
for e in errs:
    st.error(e)
SHORT = {"boe_reserves": "Reserves", "boe_apf_gilts": "APF gilts (proceeds)"}
lines = [(SHORT[k], S.window(d[k].data / 1000, start)) for k in ("boe_reserves", "boe_apf_gilts")
         if k in d]
if lines:
    warn_status(d)
    section("BoE reserve balances vs APF gilt holdings, GBP bn, WEEKLY", "GBP bn", "weekly", lines,
            stamp_lines(d), band_mode, ev("UK"),
            note="WEEKLY data, each on its own publication dates (no alignment or filling). APF "
                 "holdings are in initial purchase proceeds, not market value.",
            sources=src(d), as_of=asof(d))

# --- 5. Policy rate vs SONIA -------------------------------------------------------------------
st.subheader("SONIA versus Bank Rate")
d, errs = get(["sonia", "boe_bank_rate"])
for e in errs:
    st.error(e)
if "sonia" in d and "boe_bank_rate" in d:
    warn_status(d)
    section("SONIA minus Bank Rate, bp, daily", "bp", "daily",
            [("SONIA − Bank Rate", S.window(S.combine(d["sonia"].data, d["boe_bank_rate"].data,
                                                       100), start))],
            stamp_lines(d), band_mode, ev("UK"),
            note="Computed on dates where both are published. Both series are from the Bank of "
                 "England Database (IUDSOIA, IUDBEDR).",
            sources=src(d), as_of=asof(d))
explain("statistics on this page", """
- **Last / Min / Max / Mean / SD**: over the selected range (SD is the sample standard deviation).
- **Latest chg**: the latest observation-to-observation change at the series' own frequency
  (day, week or month). **Z of chg**: (latest change − mean change) / SD of changes, over the
  range. No 1-day statistic is computed for weekly or monthly series.
- **Level pctile**: share of observations in the range at or below the latest level.
- **Bands**: mean ± 1 and ± 2 SD of the level over the range. They describe the range of the
  data shown; they are not forecasts.
- **Events**: dates whose official page was fetched and checked (scripts/verify_events.py).
""")
