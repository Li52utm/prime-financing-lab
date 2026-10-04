"""Dated central bank events for chart shading. Each event cites an official page.

An event is shown in the app only if scripts/verify_events.py fetched its URL from this machine
and found both the event date and the expected phrase on the page (data/events_verified.json).
Nothing here is inferred: descriptions restate what the cited page announces.
"""

import json
import pathlib
from dataclasses import dataclass

VERIFIED_PATH = pathlib.Path(__file__).resolve().parent / "events_verified.json"


@dataclass(frozen=True)
class Event:
    day: str  # ISO date of the announcement
    region: str  # UK, EA (euro area) or US
    label: str
    url: str
    phrase: str  # must appear on the fetched page


EVENTS = [
    Event("2020-03-15", "US", "Fed cuts the federal funds target range to 0 to 1/4 percent",
          "https://www.federalreserve.gov/newsevents/pressreleases/monetary20200315a.htm",
          "0 to 1/4"),
    Event("2021-12-16", "UK", "Bank of England raises Bank Rate to 0.25%",
          "https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/2021/december-2021",
          "0.25%"),
    Event("2022-02-03", "UK", "Bank of England raises Bank Rate to 0.5% and stops reinvesting "
          "maturing APF gilts", "https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/"
          "2022/february-2022", "reinvest"),
    Event("2022-03-16", "US", "Fed raises the federal funds target range to 1/4 to 1/2 percent",
          "https://www.federalreserve.gov/newsevents/pressreleases/monetary20220316a.htm",
          "1/4 to 1/2"),
    Event("2022-05-04", "US", "Fed announces balance sheet reduction plans (runoff from June 1)",
          "https://www.federalreserve.gov/newsevents/pressreleases/monetary20220504b.htm",
          "June 1"),
    Event("2022-07-21", "EA", "ECB raises the three key interest rates by 50 basis points",
          "https://www.ecb.europa.eu/press/pr/date/2022/html/ecb.mp220721~53e5bdd317.en.html",
          "50 basis points"),
    Event("2022-09-22", "UK", "Bank of England MPC votes to begin gilt sales from the APF",
          "https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/2022/september-2022",
          "sales"),
    Event("2022-09-28", "UK", "Bank of England announces a temporary gilt market operation",
          "https://www.bankofengland.co.uk/news/2022/september/bank-of-england-announces-gilt-"
          "market-operation", "gilt market"),
    Event("2022-12-15", "EA", "ECB: APP portfolio to decline from March 2023 (partial "
          "non-reinvestment)", "https://www.ecb.europa.eu/press/pr/date/2022/html/"
          "ecb.mp221215~f3461d7b6e.en.html", "March 2023"),
    Event("2024-06-06", "EA", "ECB lowers the three key interest rates by 25 basis points",
          "https://www.ecb.europa.eu/press/pr/date/2024/html/ecb.mp240606~2148ecdb3c.en.html",
          "25 basis points"),
    Event("2024-08-01", "UK", "Bank of England reduces Bank Rate to 5%",
          "https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/2024/august-2024",
          "5%"),
]


def date_strings(day: str) -> list[str]:
    """How the event date can appear on BoE, ECB and Fed pages."""
    from datetime import date
    d = date.fromisoformat(day)
    return [f"{d.day} {d:%B %Y}", f"{d:%B} {d.day}, {d.year}", f"{d:%d %B %Y}",
            f"{d:%B %d}, {d.year}"]  # Fed pages zero-pad the day ("May 04, 2022")


def verified_events(regions: tuple[str, ...] | None = None) -> list[dict]:
    """Events whose source page was fetched and checked; each carries its URL and check time."""
    try:
        rows = json.loads(VERIFIED_PATH.read_text(encoding="utf-8"))["events"]
    except (OSError, ValueError, KeyError):
        return []
    out = [r for r in rows if r.get("verified")]
    return [r for r in out if regions is None or r["region"] in regions]
