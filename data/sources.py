"""One table of every data source the app uses: series, where it is used, provider, URL,
frequency, earliest date, terms and status. Built from data/source_audit.json (rates, liquidity
and FX, written by scripts/source_audit.py), the Markets series specs with their last cache
stamp, the SONIA ticket feed, the dated-event pages and the user-data route. Nothing is fetched
here."""

import json
import pathlib
from urllib.parse import quote

import pandas as pd

from data import events as EV
from data import markets as M
from data import sonia as SO

AUDIT_PATH = pathlib.Path(__file__).resolve().parent / "source_audit.json"
MARKETS_CHECKED = "2026-10-03"  # date the Markets sources were fetched and checked before use

USED_ON_MACRO = "Rates & Liquidity, Desk Brief"
USED_ON_MARKETS = {
    "ftse100": "Markets, Replay history, Forecast Lab",
    "spx": "Markets, Replay history, Forecast Lab",
    "brent": "Markets",
    "uk10y": "Markets",
    "bund10y": "Markets",
    "gbpusd": "Markets, Forecast Lab",
}
# Key facts first so they are visible at laptop width; long URL and terms text last
COLUMNS = ["Series", "Frequency", "Earliest", "Status", "Used on", "Provider", "URL", "Terms"]


def market_url(spec: M.SeriesSpec) -> str:
    if spec.provider == "yahoo":
        return f"https://finance.yahoo.com/quote/{quote(spec.code)} (via yfinance)"
    if spec.provider == "boe":
        return M.BOE_URL.format(code=spec.code)
    if spec.provider == "bundesbank":
        return M.BUNDESBANK_URL
    return M.EIA_BRENT_URL


def _market_status(key: str) -> str:
    meta_path = M._paths(key)[1]
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return (f"works (checked {MARKETS_CHECKED}); last fetched "
                f"{str(meta['fetched_at'])[:16].replace('T', ' ')}, as of {meta['as_of']}")
    except (OSError, ValueError, KeyError):
        return f"works (checked {MARKETS_CHECKED}); not fetched on this machine yet"


def read_audit(path: pathlib.Path = AUDIT_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def source_table(audit: dict) -> pd.DataFrame:
    rows = []
    for r in audit["series"]:
        rows.append({
            "Series": r["name"],
            # Brent and GBP/USD are fetched by data.markets for both pages: one row each
            "Used on": (f"Desk Brief, {USED_ON_MARKETS[r['key']]}" if r["key"] in M.SERIES
                        else USED_ON_MACRO), "Provider": r["source"],
            "URL": r["url"], "Frequency": r["frequency"], "Earliest": r.get("earliest", "-"),
            "Terms": ("TERMS UNVERIFIED. " if r["terms_unverified"] else "") + r["terms"],
            "Status": (f"works (audit {audit['run_at'][:10]}, latest {r.get('latest', '-')})"
                       if r.get("works") else f"FAILED in audit {audit['run_at'][:10]}"),
        })
    audited = {r["key"] for r in audit["series"]}
    for key, spec in M.SERIES.items():
        if key in audited:
            continue
        rows.append({
            "Series": spec.name, "Used on": USED_ON_MARKETS[key], "Provider": spec.source,
            "URL": market_url(spec), "Frequency": "daily", "Earliest": spec.earliest_verified,
            "Terms": M.TERMS[spec.provider] + (" Not an official provider."
                                               if spec.provider == "yahoo" else ""),
            "Status": _market_status(key),
        })
    rows.append({
        "Series": "SONIA (trade ticket)", "Used on": "Sidebar ticket, every financing page",
        "Provider": SO.BOE_SOURCE + "; fallback FRED IUDSOIA",
        "URL": SO.BOE_URL.split("?")[0] + " (IUDSOIA); fallback " + SO.FRED_URL,
        "Frequency": "daily (latest value only)", "Earliest": "n/a (latest value)",
        "Terms": M.TERMS["boe"],
        "Status": "BoE works; FRED fallback unreachable from the development machine",
    })
    events = EV.verified_events(("US", "UK", "EA"))
    rows.append({
        "Series": f"Dated policy events ({len(events)} of {len(EV.EVENTS)} verified)",
        "Used on": "Rates & Liquidity (shaded events)", "Provider": "Fed, Bank of England, ECB",
        "URL": "; ".join(e["url"] for e in events), "Frequency": "event dates",
        "Earliest": min((str(e["day"]) for e in events), default="-"),
        "Terms": "Official central bank web pages, linked not copied.",
        "Status": "each page fetched by scripts/verify_events.py: HTTP 200, date and phrase found",
    })
    rows.append({
        "Series": "User-supplied CSV", "Used on": "Bring your own data", "Provider": "the user",
        "URL": "n/a (upload or paste)", "Frequency": "daily, weekly or monthly",
        "Earliest": "n/a", "Terms": "The user's own data; session memory only, never written to disk.",
        "Status": "USER-SUPPLIED",
    })
    return pd.DataFrame(rows, columns=COLUMNS)


def not_used_table(audit: dict) -> pd.DataFrame:
    return pd.DataFrame([{"Source": n["name"], "URL": n["url"], "Result": n["status"]}
                         for n in audit["not_used"]])
