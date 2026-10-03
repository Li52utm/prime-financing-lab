"""Daily market history for the Markets page: fetch, parse, cache, stamp.

Every source below was fetched for real on 2026-10-03 before being used (raw first lines,
parsed result and earliest date checked). Not used: FRED (no HTTP response from the
development network) and Stooq (returns a JavaScript bot challenge, not data).

Load order (load_series): live fetch -> data/cache/markets/<key>.csv -> MarketDataError,
which the page shows as an error. Every result is stamped with source, as-of date and
status (live / cached). Nothing here feeds the financing engine.
"""

import io
import json
import pathlib
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TIMEOUT_SECONDS = 30
CACHE_DIR = pathlib.Path(__file__).resolve().parent / "cache" / "markets"

BOE_URL = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
           "?csv.x=yes&Datefrom=01/Jan/1963&Dateto=now&SeriesCodes={code}&CSVF=TN"
           "&UsingCodes=Y&VPD=Y&VFD=N")  # BoE rejects 'From' dates before 1963
BUNDESBANK_URL = ("https://api.statistiken.bundesbank.de/rest/data/BBSIS/"
                  "D.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A?format=csv&lang=en")
EIA_BRENT_URL = "https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls"

TERMS = {
    "yahoo": ("Yahoo Finance data via yfinance (not affiliated with Yahoo). Yahoo's terms: "
              "personal use only; check Yahoo's terms before any other use."),
    "boe": ("Bank of England Database: reproduction under the UK Open Government Licence; "
            "copyright the Governor and Company of the Bank of England."),
    "bundesbank": ("Deutsche Bundesbank statistics portal: freely available under its terms of "
                   "use; reproduction permitted only if the source is stated."),
    "eia": ("U.S. Energy Information Administration: public domain; acknowledge as "
            "'Source: U.S. Energy Information Administration (<date>)'."),
}


@dataclass(frozen=True)
class SeriesSpec:
    key: str
    name: str
    source: str  # shown in every stamp
    provider: str  # key into TERMS
    code: str  # ticker / series code
    unit: str
    is_yield: bool  # yields: changes in bp, drawdown as bp from peak
    has_ohlc: bool
    earliest_verified: str  # earliest observation seen when the source was verified


SERIES = {
    "ftse100": SeriesSpec("ftse100", "FTSE 100", "Yahoo Finance via yfinance (^FTSE)", "yahoo",
                          "^FTSE", "index points", False, True, "1984-01-03"),
    "spx": SeriesSpec("spx", "S&P 500", "Yahoo Finance via yfinance (^GSPC)", "yahoo",
                      "^GSPC", "index points", False, True, "1927-12-30"),
    "brent": SeriesSpec("brent", "Brent crude (spot, FOB)", "EIA, Europe Brent spot (RBRTE)",
                        "eia", "RBRTE", "USD per barrel", False, False, "1987-05-20"),
    "uk10y": SeriesSpec("uk10y", "UK 10-year gilt yield",
                        "Bank of England, 10y nominal par yield (IUDMNPY)", "boe", "IUDMNPY",
                        "% yield", True, False, "1993-11-01"),
    "bund10y": SeriesSpec("bund10y", "German 10-year Bund yield",
                          "Deutsche Bundesbank, 10y Federal securities (BBSIS, Svensson)",
                          "bundesbank", "BBSIS.D.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A",
                          "% yield", True, False, "1997-08-07"),
    "gbpusd": SeriesSpec("gbpusd", "GBP/USD", "Bank of England, spot GBP/USD (XUDLUSS)", "boe",
                         "XUDLUSS", "USD per GBP", False, False, "1975-01-02"),
}


class MarketDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class MarketSeries:
    spec: SeriesSpec
    data: pd.DataFrame = field(repr=False)  # DatetimeIndex; close (+ open/high/low/volume)
    status: str  # "live" or "cached"
    as_of: date
    fetched_at: str  # ISO timestamp of the live fetch that produced the data

    @property
    def stamp(self) -> str:
        return (f"Source: {self.spec.source} · as of {self.as_of:%d %b %Y} · status "
                f"{self.status} · fetched {self.fetched_at[:16].replace('T', ' ')}")


# --- Parsers (pure; tested offline) ---------------------------------------------------------

def _frame(dates, closes) -> pd.DataFrame:
    df = pd.DataFrame({"close": pd.to_numeric(pd.Series(closes), errors="coerce").to_numpy()},
                      index=pd.DatetimeIndex(pd.to_datetime(list(dates)), name="date"))
    df = df[df["close"].notna()]
    return df[~df.index.duplicated(keep="last")].sort_index()


def parse_boe_csv(text: str, code: str) -> pd.DataFrame:
    """'DATE,<CODE>' then 'DD Mon YYYY,value' (BoE IADB CSV, verified)."""
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines or lines[0].replace(" ", "").upper() != f"DATE,{code}".upper():
        raise ValueError(f"unexpected BoE header: {lines[:1]}")
    rows = [l.split(",") for l in lines[1:]]
    dates = [datetime.strptime(r[0].strip(), "%d %b %Y") for r in rows]
    return _frame(dates, [r[1] if len(r) > 1 else "" for r in rows])


_ISO_ROW = re.compile(r"^\d{4}-\d{2}-\d{2},")


def parse_bundesbank_csv(text: str) -> pd.DataFrame:
    """Bundesbank BBSIS CSV (verified): BOM, ~9 metadata rows, then 'YYYY-MM-DD,value,flag';
    missing days are '.' with 'No value available'."""
    rows = [l.split(",") for l in text.lstrip("﻿").splitlines() if _ISO_ROW.match(l)]
    if not rows:
        raise ValueError("no dated rows in Bundesbank response")
    return _frame([r[0] for r in rows], [r[1] for r in rows])


def parse_eia_xls(content: bytes) -> pd.DataFrame:
    """EIA RBRTEd.xls (verified): sheet 'Data 1', two title rows, then Date / price."""
    raw = pd.read_excel(io.BytesIO(content), sheet_name="Data 1", skiprows=2, engine="xlrd")
    return eia_frame(raw)


def eia_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """First two columns of the EIA 'Data 1' sheet (Date, price) -> standard frame."""
    raw = raw.iloc[:, :2].dropna()
    return _frame(raw.iloc[:, 0], raw.iloc[:, 1])


def normalise_yahoo(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance history() frame -> tz-naive daily OHLCV. Zero volume (early history) -> NaN."""
    if df is None or df.empty:
        raise ValueError("empty Yahoo response")
    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_localize(None) if idx.tz is not None else idx
    out = pd.DataFrame({
        "open": df["Open"].to_numpy(), "high": df["High"].to_numpy(),
        "low": df["Low"].to_numpy(), "close": df["Close"].to_numpy(),
        "volume": df["Volume"].astype(float).replace(0.0, float("nan")).to_numpy(),
    }, index=pd.DatetimeIndex(idx.normalize(), name="date"))
    out = out[out["close"].notna()]
    return out[~out.index.duplicated(keep="last")].sort_index()


def sanity_check(df: pd.DataFrame, spec: SeriesSpec) -> pd.DataFrame:
    if len(df) < 30:
        raise ValueError(f"only {len(df)} observations")
    lo, hi = (-5.0, 30.0) if spec.is_yield else (0.0, 1e7)
    if not df["close"].between(lo, hi).all():
        raise ValueError(f"values outside {lo}..{hi}")
    return df


# --- Live fetch (network) ------------------------------------------------------------------------

def _get(url: str, binary: bool = False, attempts: int = 2):
    """HTTP GET with one retry on network errors (dropped connections were seen in testing).
    Parse and sanity failures are not retried."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                body = resp.read()
            return body if binary else body.decode("utf-8-sig")
        except OSError:  # URLError, timeouts and connection resets are OSError subclasses
            if attempt == attempts - 1:
                raise


def _yahoo_history(symbol: str) -> pd.DataFrame:
    import yfinance as yf  # imported lazily: only needed for live equity fetches
    return yf.Ticker(symbol).history(period="max", interval="1d", auto_adjust=False)


def fetch_live(key: str) -> pd.DataFrame:
    """Fetch one series from its verified source. Raises on any failure."""
    spec = SERIES[key]
    if spec.provider == "yahoo":
        df = normalise_yahoo(_yahoo_history(spec.code))
    elif spec.provider == "boe":
        df = parse_boe_csv(_get(BOE_URL.format(code=spec.code)), spec.code)
    elif spec.provider == "bundesbank":
        df = parse_bundesbank_csv(_get(BUNDESBANK_URL))
    elif spec.provider == "eia":
        df = parse_eia_xls(_get(EIA_BRENT_URL, binary=True))
    else:
        raise ValueError(f"unknown provider {spec.provider}")
    return sanity_check(df, spec)


# --- Cache -----------------------------------------------------------------------------------

def _paths(key: str) -> tuple[pathlib.Path, pathlib.Path]:
    return CACHE_DIR / f"{key}.csv", CACHE_DIR / f"{key}.meta.json"


def write_cache(key: str, df: pd.DataFrame, fetched_at: str) -> None:
    data_path, meta_path = _paths(key)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(data_path, index_label="date")
    meta_path.write_text(json.dumps({"key": key, "source": SERIES[key].source,
                                     "fetched_at": fetched_at,
                                     "as_of": df.index[-1].date().isoformat()}), encoding="utf-8")


def read_cache(key: str) -> tuple[pd.DataFrame, str] | None:
    """(data, fetched_at) or None if missing or unreadable."""
    data_path, meta_path = _paths(key)
    try:
        df = pd.read_csv(data_path, index_col="date", parse_dates=["date"])
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return sanity_check(df, SERIES[key]), str(meta.get("fetched_at", ""))
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def load_series(key: str) -> MarketSeries:
    """Live, then cache; raises MarketDataError if neither is available."""
    spec = SERIES[key]
    try:
        df = fetch_live(key)
        fetched_at = datetime.now().isoformat(timespec="seconds")
        try:
            write_cache(key, df, fetched_at)
        except OSError:
            pass  # a read-only disk must not stop a live series being shown
        return MarketSeries(spec, df, "live", df.index[-1].date(), fetched_at)
    except Exception as live_error:
        cached = read_cache(key)
        if cached is None:
            raise MarketDataError(
                f"{spec.name}: live fetch from {spec.source} failed "
                f"({type(live_error).__name__}: {live_error}) and there is no cached copy."
            ) from live_error
        df, fetched_at = cached
        return MarketSeries(spec, df, "cached", df.index[-1].date(), fetched_at)
