"""Rates, liquidity and FX series from official public providers: fetch, parse, cache, stamp.

Every source below was fetched live from the development machine on 2026-10-04 before use;
raw first lines, parsed values, frequency and earliest date are recorded in
data/source_audit.md (scripts/source_audit.py). Not used: FRED (no HTTP response from this
machine on 2026-10-03 and 2026-10-04) and Stooq (bot challenge), so US Treasury yields come
from the US Treasury itself.

Load order (load_macro): live fetch -> data/cache/macro/<key>.csv -> MacroDataError (the page
shows the error). Nothing is interpolated or filled: missing days stay missing.
"""

import csv
import io
import json
import pathlib
import re
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from data import markets

USER_AGENT = markets.USER_AGENT
CACHE_DIR = pathlib.Path(__file__).resolve().parent / "cache" / "macro"
ECB_API = "https://data-api.ecb.europa.eu/service/data/{flow}/{key}?format=csvdata&detail=dataonly"
BOE_URL = markets.BOE_URL
BUNDESBANK_URL = "https://api.statistiken.bundesbank.de/rest/data/BBSIS/{key}?format=csv&lang=en"
UST_URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
           "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
           "&field_tdr_date_value={year}&page&_format=csv")
UST_FIRST_YEAR = 1990  # verified: the 1990 file starts 01/02/1990 with 2 Yr and 10 Yr columns

TERMS = {
    "ecb": ("ECB statistics: reusable free of charge if the source is quoted ('Source: ECB "
            "statistics') and the statistics are not modified (ESCB reuse policy)."),
    "boe": markets.TERMS["boe"],
    "bundesbank": markets.TERMS["bundesbank"],
    "ustreasury": ("US Treasury (home.treasury.gov). Terms unverified: no reuse statement found; "
                   "US federal government data is generally public domain."),
    "eia": markets.TERMS["eia"],
}
TERMS_UNVERIFIED = {"ustreasury"}


@dataclass(frozen=True)
class MacroSpec:
    key: str
    name: str
    provider: str  # ecb, boe, bundesbank, ustreasury, markets (delegates to data.markets)
    code: str
    unit: str
    frequency: str  # daily, weekly, monthly (as published)
    earliest_verified: str
    source: str
    note: str = ""


def _ecb(key, name, flow, code, unit, freq, earliest, note=""):
    return MacroSpec(key, name, "ecb", f"{flow}/{code}", unit, freq, earliest,
                     f"ECB Data Portal ({flow}.{code})", note)


def _boe(key, name, code, unit, freq, earliest, note=""):
    return MacroSpec(key, name, "boe", code, unit, freq, earliest,
                     f"Bank of England Database ({code})", note)


SERIES = {s.key: s for s in [
    _ecb("ea_aaa_2y", "Euro area AAA govt 2y yield", "YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y",
         "%", "daily", "2004-09-06", "Svensson spot rate, AAA-rated euro area central government"),
    _ecb("ea_aaa_10y", "Euro area AAA govt 10y yield", "YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y",
         "%", "daily", "2004-09-06", "Svensson spot rate, AAA-rated euro area central government"),
    _ecb("estr", "Euro short-term rate (€STR)", "EST", "B.EU000A2X2A25.WT", "%", "daily",
         "2019-10-01", "Volume-weighted trimmed mean rate"),
    _ecb("ecb_exliq", "Eurosystem excess liquidity", "ILM", "D.U2.C.EXLIQ.U2.EUR", "EUR million",
         "daily", "2024-09-27", "Official series; only published from 2024-09-27"),
    _ecb("ecb_df", "Eurosystem deposit facility", "ILM", "D.U2.C.L020200.U2.EUR", "EUR million",
         "daily", "1998-12-31"),
    _ecb("ecb_ca", "Credit institutions' current accounts", "ILM", "D.U2.C.L020100.U2.EUR",
         "EUR million", "daily", "1998-12-31"),
    _ecb("ecb_mlf", "Eurosystem marginal lending facility", "ILM", "D.U2.C.A050500.U2.EUR",
         "EUR million", "daily", "1998-12-31"),
    _ecb("ecb_mrr", "Eurosystem minimum reserve requirements", "ILM", "D.U2.C.MRR.U2.EUR",
         "EUR million", "daily", "2024-09-27", "Daily series only from 2024-09-27"),
    _ecb("de_10y_m", "Germany 10y government yield (monthly)", "IRS",
         "M.DE.L.L40.CI.0000.EUR.N.Z", "%", "monthly", "1990-01",
         "Long-term interest rate for convergence purposes; monthly, dated to the 1st"),
    _ecb("fr_10y_m", "France 10y government yield (monthly)", "IRS",
         "M.FR.L.L40.CI.0000.EUR.N.Z", "%", "monthly", "1986-01",
         "Long-term interest rate for convergence purposes; monthly, dated to the 1st"),
    _ecb("it_10y_m", "Italy 10y government yield (monthly)", "IRS",
         "M.IT.L.L40.CI.0000.EUR.N.Z", "%", "monthly", "1991-03",
         "Long-term interest rate for convergence purposes; monthly, dated to the 1st"),
    _ecb("eurusd", "EUR/USD (ECB reference rate)", "EXR", "D.USD.EUR.SP00.A", "USD per EUR",
         "daily", "1999-01-04", "2.15pm CET reference rate"),
    _boe("boe_bank_rate", "Bank of England Bank Rate", "IUDBEDR", "%", "daily", "1975-01-02",
         "Official Bank Rate"),
    _boe("sonia", "SONIA", "IUDSOIA", "%", "daily", "1997-01-02"),
    _boe("uk_5y", "UK 5y gilt nominal par yield", "IUDSNPY", "%", "daily", "1993-12-01"),
    _boe("uk_10y", "UK 10y gilt nominal par yield", "IUDMNPY", "%", "daily", "1993-11-01"),
    _boe("uk_20y", "UK 20y gilt nominal par yield", "IUDLNPY", "%", "daily", "2000-01-04"),
    _boe("boe_reserves", "BoE sterling reserve balances", "RPWB56A", "GBP million", "weekly",
         "2006-05-24", "Weekly amounts outstanding of central bank reserve balance liabilities, NSA"),
    _boe("boe_apf_gilts", "APF gilt holdings (purchase proceeds)", "YWWB9T9", "GBP million",
         "weekly", "2009-03-12", "Measured in initial purchase proceeds, not market value"),
    MacroSpec("de_2y", "Germany 2y Bund yield (daily)", "bundesbank",
              "D.I.ZST.ZI.EUR.S1311.B.A604.R02XX.R.A.A._Z._Z.A", "%", "daily", "1997-08-07",
              "Deutsche Bundesbank (BBSIS, Svensson, 2y)"),
    MacroSpec("de_10y", "Germany 10y Bund yield (daily)", "bundesbank",
              "D.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A", "%", "daily", "1997-08-07",
              "Deutsche Bundesbank (BBSIS, Svensson, 10y)"),
    MacroSpec("us_2y", "US Treasury 2y par yield", "ustreasury", "2 Yr", "%", "daily",
              "1990-01-02", "US Treasury, Daily Treasury Par Yield Curve Rates (2 Yr)"),
    MacroSpec("us_10y", "US Treasury 10y par yield", "ustreasury", "10 Yr", "%", "daily",
              "1990-01-02", "US Treasury, Daily Treasury Par Yield Curve Rates (10 Yr)"),
    MacroSpec("brent", "Brent crude (spot, FOB)", "markets", "brent", "USD per barrel", "daily",
              "1987-05-20", markets.SERIES["brent"].source),
    MacroSpec("gbpusd", "GBP/USD", "markets", "gbpusd", "USD per GBP", "daily", "1975-01-02",
              markets.SERIES["gbpusd"].source),
]}
PROVIDER_TERMS = {"ecb": "ecb", "boe": "boe", "bundesbank": "bundesbank",
                  "ustreasury": "ustreasury", "markets": None}


def terms_for(spec: MacroSpec) -> str:
    if spec.provider == "markets":
        return markets.TERMS[markets.SERIES[spec.code].provider]
    return TERMS[spec.provider]


class MacroDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class MacroSeries:
    spec: MacroSpec
    data: pd.Series = field(repr=False)  # DatetimeIndex -> value; no filling
    status: str  # live or cached
    as_of: date
    fetched_at: str

    @property
    def stamp(self) -> str:
        return (f"Source: {self.spec.source} · {self.spec.frequency} · as of {self.as_of:%d %b %Y}"
                f" · status {self.status} · fetched {self.fetched_at[:16].replace('T', ' ')}")


# --- Parsers (pure; tested offline) -------------------------------------------------------------

def _series(dates, values) -> pd.Series:
    s = pd.Series(pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(),
                  index=pd.DatetimeIndex(pd.to_datetime(list(dates)), name="date"), name="value")
    s = s[s.notna()]
    return s[~s.index.duplicated(keep="last")].sort_index()


def parse_ecb_csv(text: str) -> pd.Series:
    """ECB csvdata (detail=dataonly): columns include TIME_PERIOD and OBS_VALUE. Monthly periods
    (YYYY-MM) are dated to the first of the month; weekly (YYYY-Www) to that ISO week's Monday."""
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if not rows or "TIME_PERIOD" not in rows[0]:
        raise ValueError("unexpected ECB response")
    def to_date(p: str) -> str:
        if re.fullmatch(r"\d{4}-\d{2}", p):
            return p + "-01"
        m = re.fullmatch(r"(\d{4})-W(\d{2})", p)
        if m:
            return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1).isoformat()
        return p
    return _series([to_date(r["TIME_PERIOD"]) for r in rows], [r["OBS_VALUE"] for r in rows])


def parse_boe_csv(text: str, code: str) -> pd.Series:
    df = markets.parse_boe_csv(text, code)
    return df["close"].rename("value")


def parse_bundesbank_csv(text: str) -> pd.Series:
    return markets.parse_bundesbank_csv(text)["close"].rename("value")


def parse_ust_csv(text: str, column: str) -> pd.Series:
    """US Treasury par yield CSV: 'Date,"1 Mo",...,"2 Yr",...' with MM/DD/YYYY dates, newest first."""
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if not rows or column not in rows[0]:
        raise ValueError(f"column {column!r} not in US Treasury file")
    return _series([datetime.strptime(r["Date"], "%m/%d/%Y") for r in rows],
                   [r[column] for r in rows])


def sanity_check(s: pd.Series, spec: MacroSpec) -> pd.Series:
    if len(s) < 10:
        raise ValueError(f"only {len(s)} observations")
    if spec.unit == "%" and not s.between(-5, 30).all():
        raise ValueError("rate outside -5%..30%")
    if spec.unit.endswith("million") and (s < -1e8).any():
        raise ValueError("implausible amount")
    return s


# --- Live fetch ----------------------------------------------------------------------------------

def _get(url: str, attempts: int = 4, timeout: int = 60) -> str:
    """GET with retries and backoff: the ECB API returned intermittent 504s during testing."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8-sig")
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))


def _fetch_ust(column: str, cached: pd.Series | None, today: date | None = None) -> pd.Series:
    """US Treasury publishes one file per year. With a cache, refetch only the last two years and
    merge (newer values win); without one, fetch every year from 1990."""
    year = (today or date.today()).year
    first = year - 1 if cached is not None and len(cached) else UST_FIRST_YEAR
    parts = [cached] if cached is not None and first > UST_FIRST_YEAR else []
    for y in range(first, year + 1):
        parts.append(parse_ust_csv(_get(UST_URL.format(year=y)), column))
    s = pd.concat(parts)
    return s[~s.index.duplicated(keep="last")].sort_index()


def fetch_live(key: str) -> pd.Series:
    spec = SERIES[key]
    if spec.provider == "ecb":
        flow, code = spec.code.split("/", 1)
        s = parse_ecb_csv(_get(ECB_API.format(flow=flow, key=code)))
    elif spec.provider == "boe":
        s = parse_boe_csv(_get(BOE_URL.format(code=spec.code)), spec.code)
    elif spec.provider == "bundesbank":
        s = parse_bundesbank_csv(_get(BUNDESBANK_URL.format(key=spec.code)))
    elif spec.provider == "ustreasury":
        cached = read_cache(key)
        s = _fetch_ust(spec.code, cached[0] if cached else None)
    elif spec.provider == "markets":
        s = markets.fetch_live(spec.code)["close"].rename("value")
    else:
        raise ValueError(f"unknown provider {spec.provider}")
    return sanity_check(s, spec)


# --- Cache ----------------------------------------------------------------------------------------

def _paths(key: str):
    return CACHE_DIR / f"{key}.csv", CACHE_DIR / f"{key}.meta.json"


def write_cache(key: str, s: pd.Series, fetched_at: str) -> None:
    data_path, meta_path = _paths(key)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    s.rename("value").to_csv(data_path, index_label="date")
    meta_path.write_text(json.dumps({"key": key, "fetched_at": fetched_at,
                                     "as_of": s.index[-1].date().isoformat(),
                                     "source": SERIES[key].source}), encoding="utf-8")


def read_cache(key: str) -> tuple[pd.Series, str] | None:
    data_path, meta_path = _paths(key)
    try:
        df = pd.read_csv(data_path, index_col="date", parse_dates=["date"])
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return sanity_check(df["value"], SERIES[key]), str(meta.get("fetched_at", ""))
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def load_macro(key: str) -> MacroSeries:
    """Live, then cache; raises MacroDataError if neither is available."""
    spec = SERIES[key]
    try:
        s = fetch_live(key)
        fetched_at = datetime.now().isoformat(timespec="seconds")
        try:
            write_cache(key, s, fetched_at)
        except OSError:
            pass
        return MacroSeries(spec, s, "live", s.index[-1].date(), fetched_at)
    except Exception as live_error:
        cached = read_cache(key)
        if cached is None:
            raise MacroDataError(f"{spec.name}: live fetch from {spec.source} failed "
                                 f"({type(live_error).__name__}: {live_error}) and there is no "
                                 "cached copy.") from live_error
        s, fetched_at = cached
        return MacroSeries(spec, s, "cached", s.index[-1].date(), fetched_at)
