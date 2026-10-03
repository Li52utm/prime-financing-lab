"""Live SONIA (Bank of England series IUDSOIA) with cache and placeholder fallback.

Sources, both verified on 2026-10-03 by fetching them:
- Bank of England IADB CSV. Response "DATE,IUDSOIA" then rows like "30 Sep 2026,3.7329"
  (percent). Weekends and holidays have no row.
- FRED CSV (fallback). Response "observation_date,IUDSOIA" then rows like
  "2026-09-30,3.7329". UK holidays appear with an empty value. FRED did not respond from
  the development machine's network (TCP/TLS connected, no HTTP response); its format was
  verified via a fetch from another network.

Load order (load_sonia): live fetch -> data/cache/sonia.json -> assumptions.SONIA.
The engine never calls this module: SONIA is passed into the engine as an input.
"""

import csv
import io
import json
import pathlib
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np

import assumptions as A

BOE_URL = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
           "?csv.x=yes&Datefrom={date_from}&Dateto=now&SeriesCodes=IUDSOIA&CSVF=TN"
           "&UsingCodes=Y&VPD=Y&VFD=N")
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=IUDSOIA"
BOE_SOURCE = "Bank of England IADB (IUDSOIA)"
FRED_SOURCE = "FRED (IUDSOIA)"
PLACEHOLDER_SOURCE = "assumptions.py placeholder"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TIMEOUT_SECONDS = 10
LOOKBACK_DAYS = 60  # BoE request window; plenty to find the latest published fixing
SANITY_MIN, SANITY_MAX = 0.0, 0.15  # reject values outside 0% to 15%
STALE_BUSINESS_DAYS = 5
CACHE_PATH = pathlib.Path(__file__).resolve().parent / "cache" / "sonia.json"


class SoniaFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class SoniaQuote:
    rate: float  # decimal (0.037329 = 3.7329%)
    as_of: date | None  # None for the placeholder
    source: str
    status: str  # "live", "cached" or "fallback"
    age_days: int | None  # calendar days from as_of to today
    business_days_old: int | None  # weekdays from as_of to today (no holiday calendar)

    @property
    def stale(self) -> bool:
        return (self.status != "live" or self.business_days_old is None
                or self.business_days_old > STALE_BUSINESS_DAYS)


# --- Parsing -----------------------------------------------------------------------------

def _latest(rows: list[tuple[date, str]]) -> tuple[float, date]:
    """Most recent observation with a non-empty value, as a decimal, sanity-checked."""
    valid = [(d, v.strip()) for d, v in rows if v and v.strip() not in ("", ".")]
    if not valid:
        raise ValueError("no observations with a value")
    as_of, value = max(valid, key=lambda r: r[0])
    rate = float(value) / 100
    if not SANITY_MIN <= rate <= SANITY_MAX:
        raise ValueError(f"SONIA {rate:.4%} on {as_of} is outside {SANITY_MIN:.0%}-{SANITY_MAX:.0%}")
    return rate, as_of


def _rows(text: str, date_format: str) -> list[tuple[date, str]]:
    reader = csv.reader(io.StringIO(text.strip()))
    header = next(reader, None)
    if not header or len(header) < 2 or "IUDSOIA" not in header[1].upper():
        raise ValueError(f"unexpected header: {header}")
    out = []
    for row in reader:
        if not row or not row[0].strip():
            continue
        out.append((datetime.strptime(row[0].strip(), date_format).date(),
                    row[1] if len(row) > 1 else ""))
    return out


def parse_boe_csv(text: str) -> tuple[float, date]:
    """'DATE,IUDSOIA' then 'DD Mon YYYY,percent'."""
    return _latest(_rows(text, "%d %b %Y"))


def parse_fred_csv(text: str) -> tuple[float, date]:
    """'observation_date,IUDSOIA' then 'YYYY-MM-DD,percent' (empty on holidays)."""
    return _latest(_rows(text, "%Y-%m-%d"))


# --- Fetching ----------------------------------------------------------------------------

def boe_url(today: date | None = None) -> str:
    start = (today or date.today()) - timedelta(days=LOOKBACK_DAYS)
    return BOE_URL.format(date_from=start.strftime("%d/%b/%Y"))


def http_get(url: str, timeout: float = TIMEOUT_SECONDS) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "text/csv,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8-sig")


def fetch_latest_sonia(getter=None, today: date | None = None) -> tuple[float, date, str]:
    """(rate_as_decimal, as_of_date, source_name). BoE first, then FRED.
    Raises SoniaFetchError if neither returns a sane value."""
    getter = getter or http_get
    errors = []
    for source, url, parser in ((BOE_SOURCE, boe_url(today), parse_boe_csv),
                                (FRED_SOURCE, FRED_URL, parse_fred_csv)):
        try:
            rate, as_of = parser(getter(url))
            return rate, as_of, source
        except Exception as e:  # network, HTTP, parse or sanity failure: try the next source
            errors.append(f"{source}: {type(e).__name__}: {e}")
    raise SoniaFetchError("; ".join(errors))


# --- Cache -------------------------------------------------------------------------------

def write_cache(rate: float, as_of: date, source: str, path: pathlib.Path | None = None) -> None:
    path = path or CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rate": rate, "as_of": as_of.isoformat(), "source": source,
                                "saved_at": datetime.now().isoformat(timespec="seconds")}),
                    encoding="utf-8")


def read_cache(path: pathlib.Path | None = None) -> tuple[float, date, str] | None:
    """The cached (rate, as_of, source), or None if missing, unreadable or not sane."""
    path = path or CACHE_PATH
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        rate, as_of = float(d["rate"]), date.fromisoformat(d["as_of"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not SANITY_MIN <= rate <= SANITY_MAX:
        return None
    return rate, as_of, str(d.get("source", "cache"))


# --- Load order ----------------------------------------------------------------------------

def _quote(rate: float, as_of: date | None, source: str, status: str,
           today: date) -> SoniaQuote:
    if as_of is None:
        return SoniaQuote(rate, None, source, status, None, None)
    return SoniaQuote(rate, as_of, source, status, (today - as_of).days,
                      int(np.busday_count(as_of, today)))


def load_sonia(today: date | None = None) -> SoniaQuote:
    """Live fetch, then the cache, then the assumptions.py placeholder."""
    today = today or date.today()
    try:
        rate, as_of, source = fetch_latest_sonia(today=today)
        try:
            write_cache(rate, as_of, source, CACHE_PATH)
        except OSError:
            pass  # a read-only disk must not stop a live value being used
        return _quote(rate, as_of, source, "live", today)
    except SoniaFetchError:
        pass
    cached = read_cache(CACHE_PATH)
    if cached:
        rate, as_of, source = cached
        return _quote(rate, as_of, source, "cached", today)
    return _quote(A.SONIA, None, PLACEHOLDER_SOURCE, "fallback", today)
