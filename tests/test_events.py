"""Every shaded event has an official source that was fetched and checked."""

from urllib.parse import urlparse

from data import events as EV

OFFICIAL = ("www.bankofengland.co.uk", "www.ecb.europa.eu", "www.federalreserve.gov")


def test_every_event_has_official_source_url():
    for e in EV.EVENTS:
        assert urlparse(e.url).scheme == "https" and urlparse(e.url).netloc in OFFICIAL
        assert e.phrase and e.label and e.region in ("UK", "EA", "US")


def test_shown_events_are_verified_with_date_and_phrase_found():
    shown = EV.verified_events()
    assert len(shown) == len(EV.EVENTS)  # all 11 verified on 2026-10-04
    for r in shown:
        assert r["verified"] and r["http"] == 200 and r["phrase_found"]
        assert r["date_found"] in EV.date_strings(r["day"])
        assert r["url"].startswith("https://")


def test_region_filter():
    assert {r["region"] for r in EV.verified_events(("UK",))} == {"UK"}


def test_date_strings_formats():
    assert EV.date_strings("2022-05-04") == ["4 May 2022", "May 4, 2022", "04 May 2022",
                                             "May 04, 2022"]
