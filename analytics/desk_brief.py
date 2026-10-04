"""Desk Brief: a rules-based readout of the app's own official series. Every sentence is built by
an explicit rule from numbers computed here, with the numbers inline. Nothing is a forecast.

Rules (hand-checked in tests/test_desk_brief.py):
- Statistics per series come from analytics.series_stats over the chosen history window, at the
  series' own frequency (no daily statistic for weekly or monthly data).
- Level status: "stretched" if |level z| > BRIEF_STRETCH_Z, else "normal".
  Move status: "stretched" if |change z| > BRIEF_STRETCH_Z, else "normal".
- Largest movers: series ranked by |change z| (z puts different units on one scale).
- Funding conditions compare the latest value with the last observation on or before
  (latest date - BRIEF_COMPARE_DAYS); monthly series compare with the previous month.
- Direction words come from the sign of the change: higher, lower or unchanged (exactly zero).
"""

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

import assumptions as A
from analytics import series_stats as S

D = dict[str, pd.Series]


@dataclass(frozen=True)
class BriefSeries:
    key: str
    group: str
    label: str
    unit: str  # unit of the level
    frequency: str
    deps: tuple[str, ...]  # data.macro keys
    build: Callable[[D], pd.Series]
    change_unit: str  # unit of the change ("bp" for yields quoted in %)
    change_scale: float = 1.0  # level change x scale = change in change_unit


def _raw(k, scale=1.0):
    return lambda d: d[k] * scale


def _diff(a, b):
    return lambda d: S.combine(d[a], d[b], 100)  # % minus % -> bp, common dates only


def _held(d):
    held = S.combine(d["ecb_df"], -d["ecb_ca"])  # DF - (-CA) = DF + CA, common dates only
    return S.combine(held, d["ecb_mlf"]) / 1000


def _y(key, label, group, freq="daily"):
    return BriefSeries(key, group, label, "%", freq, (key,), _raw(key), "bp", 100.0)


POLICY, LIQ, CURVE, SPREAD, FX = ("Policy and money market", "Liquidity", "Government curves",
                                  "Sovereign spreads", "FX and commodities")

UNIVERSE: list[BriefSeries] = [
    _y("boe_bank_rate", "Bank Rate", POLICY),
    _y("sonia", "SONIA", POLICY),
    BriefSeries("sonia_bank", POLICY, "SONIA − Bank Rate", "bp", "daily",
                ("sonia", "boe_bank_rate"), _diff("sonia", "boe_bank_rate"), "bp"),
    _y("estr", "€STR", POLICY),
    BriefSeries("ecb_exliq", LIQ, "Euro excess liquidity (official)", "EUR bn", "daily",
                ("ecb_exliq",), _raw("ecb_exliq", 1 / 1000), "EUR bn"),
    BriefSeries("ecb_held", LIQ, "Eurosystem DF + CA − MLF", "EUR bn", "daily",
                ("ecb_df", "ecb_ca", "ecb_mlf"), _held, "EUR bn"),
    BriefSeries("boe_reserves", LIQ, "BoE reserve balances", "GBP bn", "weekly",
                ("boe_reserves",), _raw("boe_reserves", 1 / 1000), "GBP bn"),
    BriefSeries("boe_apf_gilts", LIQ, "APF gilt holdings (proceeds)", "GBP bn", "weekly",
                ("boe_apf_gilts",), _raw("boe_apf_gilts", 1 / 1000), "GBP bn"),
    _y("us_2y", "US 2y", CURVE), _y("us_10y", "US 10y", CURVE),
    _y("ea_aaa_2y", "Euro area AAA 2y", CURVE), _y("ea_aaa_10y", "Euro area AAA 10y", CURVE),
    _y("de_2y", "Germany 2y", CURVE), _y("de_10y", "Germany 10y", CURVE),
    _y("uk_5y", "UK 5y", CURVE), _y("uk_10y", "UK 10y", CURVE), _y("uk_20y", "UK 20y", CURVE),
    BriefSeries("us_2s10s", CURVE, "US 2s10s", "bp", "daily", ("us_10y", "us_2y"),
                _diff("us_10y", "us_2y"), "bp"),
    BriefSeries("ea_2s10s", CURVE, "Euro area AAA 2s10s", "bp", "daily",
                ("ea_aaa_10y", "ea_aaa_2y"), _diff("ea_aaa_10y", "ea_aaa_2y"), "bp"),
    BriefSeries("de_2s10s", CURVE, "Germany 2s10s", "bp", "daily", ("de_10y", "de_2y"),
                _diff("de_10y", "de_2y"), "bp"),
    BriefSeries("fr_de", SPREAD, "France − Germany 10y", "bp", "monthly",
                ("fr_10y_m", "de_10y_m"), _diff("fr_10y_m", "de_10y_m"), "bp"),
    BriefSeries("it_de", SPREAD, "Italy − Germany 10y", "bp", "monthly",
                ("it_10y_m", "de_10y_m"), _diff("it_10y_m", "de_10y_m"), "bp"),
    BriefSeries("eurusd", FX, "EUR/USD", "USD per EUR", "daily", ("eurusd",), _raw("eurusd"),
                "USD per EUR"),
    BriefSeries("gbpusd", FX, "GBP/USD", "USD per GBP", "daily", ("gbpusd",), _raw("gbpusd"),
                "USD per GBP"),
    BriefSeries("brent", FX, "Brent crude", "USD per barrel", "daily", ("brent",), _raw("brent"),
                "USD per barrel"),
]


def all_deps() -> list[str]:
    return list(dict.fromkeys(k for b in UNIVERSE for k in b.deps))


def status(z: float) -> str:
    return "stretched" if S.is_stretched(z, A.BRIEF_STRETCH_Z) else "normal"


def brief_row(b: BriefSeries, s: pd.Series) -> dict:
    """Latest level, change, z-scores and percentile over the window given, plus statuses."""
    st_ = S.series_stats(s, b.frequency)
    return {
        "Group": b.group, "Series": b.label, "Frequency": b.frequency, "Unit": b.unit,
        "As of": st_["as_of"], "From": st_["first_date"], "Obs": st_["n"],
        "Last": st_["last"], "Change": st_["change"] * b.change_scale,
        "Change unit": b.change_unit, "Change per": st_["period"],
        "Change z": st_["change_z"], "Level z": st_["level_z"], "Percentile": st_["level_pct"],
        "Level status": status(st_["level_z"]), "Move status": status(st_["change_z"]),
        "key": b.key,
    }


def build_rows(data: D, start=None) -> tuple[pd.DataFrame, list[str]]:
    """One row per series whose inputs loaded; the second value lists skipped series and why."""
    rows, skipped = [], []
    for b in UNIVERSE:
        missing = [k for k in b.deps if k not in data]
        if missing:
            skipped.append(f"{b.label}: not available (failed to load: {', '.join(missing)}).")
            continue
        s = S.window(b.build(data).dropna(), start)
        if len(s) < 3:
            skipped.append(f"{b.label}: fewer than 3 observations in the window.")
            continue
        rows.append(brief_row(b, s))
    return pd.DataFrame(rows), skipped


def _num(x: float, unit: str) -> str:
    if unit == "bp":
        return f"{x:,.1f} bp"
    if unit == "%":
        return f"{x:.3f}%"
    if unit.startswith(("EUR bn", "GBP bn")):
        return f"{unit[:3]} {x:,.1f} bn"
    return f"{x:,.4f} {unit}" if abs(x) < 10 else f"{x:,.2f} {unit}"


def _chg(x: float, unit: str) -> str:
    sign = "+" if x > 0 else "−" if x < 0 else "±"
    return sign + _num(abs(x), unit)


def _ord(p: float) -> str:
    n = int(round(p))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def row_sentence(r: dict) -> str:
    return (f"{r['Series']} stood at {_num(r['Last'], r['Unit'])} on {r['As of']:%d %b %Y}, "
            f"{_chg(r['Change'], r['Change unit'])} on the {r['Change per']} "
            f"(change z {r['Change z']:+.2f}, {r['Move status']}). The level is at the "
            f"{_ord(r['Percentile'])} percentile of {r['Obs']:,} {r['Frequency']} observations "
            f"since {r['From']:%d %b %Y} (level z {r['Level z']:+.2f}, {r['Level status']}).")


def movers(rows: pd.DataFrame, n: int = A.BRIEF_TOP_MOVERS) -> pd.DataFrame:
    if rows.empty:
        return rows
    ok = rows[np.isfinite(rows["Change z"])]
    return ok.reindex(ok["Change z"].abs().sort_values(ascending=False).index).head(n)


def mover_sentence(r: dict) -> str:
    return (f"{r['Series']}: {_chg(r['Change'], r['Change unit'])} on the latest "
            f"{r['Change per']} to {r['As of']:%d %b %Y}, change z {r['Change z']:+.2f} "
            f"({r['Frequency']} data).")


def change_since(s: pd.Series, days: int, frequency: str) -> dict | None:
    """Latest value against the last observation on or before (latest - days); monthly series use
    the previous observation. None if there is no earlier observation."""
    s = s.dropna()
    if len(s) < 2:
        return None
    end = s.index[-1]
    if frequency == "monthly":
        prev = s.iloc[:-1]
    else:
        prev = s[s.index <= end - pd.Timedelta(days=days)]
    if prev.empty:
        return None
    return {"end": end.date(), "last": float(s.iloc[-1]), "start": prev.index[-1].date(),
            "prev": float(prev.iloc[-1]), "change": float(s.iloc[-1] - prev.iloc[-1])}


def _direction(x: float) -> str:
    return "higher" if x > 0 else "lower" if x < 0 else "unchanged"


FUNDING = ["sonia_bank", "ecb_exliq", "ecb_held", "boe_reserves", "us_2s10s", "ea_2s10s",
           "de_2s10s", "fr_de", "it_de"]


def funding_sentences(data: D, days: int = A.BRIEF_COMPARE_DAYS) -> list[str]:
    """Changes in funding conditions, one sentence per available series."""
    out = []
    spec = {b.key: b for b in UNIVERSE}
    for key in FUNDING:
        b = spec[key]
        if any(k not in data for k in b.deps):
            continue
        c = change_since(b.build(data), days, b.frequency)
        if c is None:
            continue
        chg = c["change"] * b.change_scale
        base = "the previous month" if b.frequency == "monthly" else f"on {c['start']:%d %b %Y}"
        move = (f"unchanged from {base}" if chg == 0 else
                f"{_num(abs(chg), b.change_unit)} {_direction(chg)} than {base}")
        when = f"{c['start']:%b %Y}" if b.frequency == "monthly" else "then"
        text = (f"{b.label} stood at {_num(c['last'], b.unit)} on {c['end']:%d %b %Y}, {move} "
                f"({_num(c['prev'], b.unit)} {when}).")
        if key.endswith("2s10s"):
            text += " The curve is " + ("inverted (10y below 2y)." if c["last"] < 0 else
                                        "flat (10y equal to 2y)." if c["last"] == 0 else
                                        "positively sloped (10y above 2y).")
        if key in ("ecb_exliq", "ecb_held", "boe_reserves") and c["prev"] != 0:
            text += f" That is {chg / c['prev'] * 100:+.1f}% over the period."
        out.append(text)
    return out
