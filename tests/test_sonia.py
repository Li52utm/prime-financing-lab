"""Offline tests for data/sonia.py (live SONIA). No test touches the network."""

import json
from datetime import date, timedelta

import pytest

import assumptions as A
from data import sonia as S

# conftest replaces fetch_latest_sonia with a network-disabled stub; keep the real one for
# the tests that exercise source ordering with a mocked getter (still no network).
REAL_FETCH = S.fetch_latest_sonia

# Samples in the formats verified on 2026-10-03.
BOE_SAMPLE = "DATE,IUDSOIA\n28 Sep 2026,3.7302\n29 Sep 2026,3.7321\n30 Sep 2026,3.7329\n"
FRED_SAMPLE = ("observation_date,IUDSOIA\n2026-08-28,3.7310\n2026-08-31,\n2026-09-01,3.7302\n"
               "2026-09-30,3.7329\n")


# --- Parsers ---------------------------------------------------------------------------------

def test_parse_boe_csv():
    assert S.parse_boe_csv(BOE_SAMPLE) == (pytest.approx(0.037329), date(2026, 9, 30))


def test_parse_fred_csv():
    assert S.parse_fred_csv(FRED_SAMPLE) == (pytest.approx(0.037329), date(2026, 9, 30))


def test_blank_and_holiday_rows_skipped():
    # BoE: trailing blank values; FRED: empty and '.' on the most recent dates
    boe = BOE_SAMPLE + "01 Oct 2026,\n02 Oct 2026, \n\n"
    assert S.parse_boe_csv(boe) == (pytest.approx(0.037329), date(2026, 9, 30))
    fred = FRED_SAMPLE + "2026-10-01,\n2026-10-02,.\n"
    assert S.parse_fred_csv(fred) == (pytest.approx(0.037329), date(2026, 9, 30))
    # a holiday in the middle (2026-08-31 empty) does not stop later dates being used
    assert S.parse_fred_csv("observation_date,IUDSOIA\n2026-08-28,3.7310\n2026-08-31,\n")[1] == \
        date(2026, 8, 28)


def test_latest_by_date_not_by_row_order():
    unordered = "DATE,IUDSOIA\n30 Sep 2026,3.7329\n28 Sep 2026,3.7302\n"
    assert S.parse_boe_csv(unordered)[1] == date(2026, 9, 30)


@pytest.mark.parametrize("value", ["16.0", "-0.25", "150"])
def test_sanity_bounds_reject(value):
    with pytest.raises(ValueError):
        S.parse_boe_csv(f"DATE,IUDSOIA\n30 Sep 2026,{value}\n")


def test_sanity_bounds_inclusive():
    assert S.parse_boe_csv("DATE,IUDSOIA\n30 Sep 2026,15\n")[0] == pytest.approx(0.15)
    assert S.parse_boe_csv("DATE,IUDSOIA\n30 Sep 2026,0\n")[0] == 0.0


def test_unexpected_header_or_empty():
    with pytest.raises(ValueError):
        S.parse_boe_csv("<html>Error</html>")
    with pytest.raises(ValueError):
        S.parse_boe_csv("DATE,IUDSOIA\n01 Oct 2026,\n")


def test_boe_url_window():
    url = S.boe_url(date(2026, 10, 3))
    assert "SeriesCodes=IUDSOIA" in url and "CSVF=TN" in url
    assert "Datefrom=04/Aug/2026" in url  # 60 days back


# --- Source order (getter mocked) ---------------------------------------------------------------

def test_fetch_prefers_boe():
    def getter(url):
        return BOE_SAMPLE if "bankofengland" in url else pytest.fail("FRED should not be called")
    assert REAL_FETCH(getter) == (pytest.approx(0.037329), date(2026, 9, 30),
                                            S.BOE_SOURCE)


def test_fetch_falls_back_to_fred_on_error_or_bad_value():
    def boe_times_out(url):
        if "bankofengland" in url:
            raise TimeoutError("timed out")
        return FRED_SAMPLE
    assert REAL_FETCH(boe_times_out)[2] == S.FRED_SOURCE

    def boe_insane(url):
        return "DATE,IUDSOIA\n30 Sep 2026,99\n" if "bankofengland" in url else FRED_SAMPLE
    assert REAL_FETCH(boe_insane)[2] == S.FRED_SOURCE


def test_fetch_raises_when_both_fail():
    def down(url):
        raise OSError("network down")
    with pytest.raises(S.SoniaFetchError, match="Bank of England.*FRED"):
        REAL_FETCH(down)


# --- Cache ---------------------------------------------------------------------------------------

def test_cache_round_trip(tmp_path):
    path = tmp_path / "c" / "sonia.json"
    S.write_cache(0.037329, date(2026, 9, 30), S.BOE_SOURCE, path)
    assert S.read_cache(path) == (pytest.approx(0.037329), date(2026, 9, 30), S.BOE_SOURCE)
    assert json.loads(path.read_text())["as_of"] == "2026-09-30"


def test_cache_missing_corrupt_or_insane(tmp_path):
    assert S.read_cache(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert S.read_cache(bad) is None
    bad.write_text(json.dumps({"rate": 0.5, "as_of": "2026-09-30", "source": "x"}))
    assert S.read_cache(bad) is None


# --- Load order: live -> cache -> placeholder --------------------------------------------------

TODAY = date(2026, 10, 3)  # Saturday


def test_load_live_writes_cache(monkeypatch):
    monkeypatch.setattr(S, "fetch_latest_sonia",
                        lambda **kw: (0.037329, date(2026, 9, 30), S.BOE_SOURCE))
    q = S.load_sonia(TODAY)
    assert (q.status, q.rate, q.source) == ("live", pytest.approx(0.037329), S.BOE_SOURCE)
    assert q.age_days == 3
    assert q.business_days_old == 3  # Wed, Thu, Fri
    assert not q.stale
    assert S.read_cache(S.CACHE_PATH)[1] == date(2026, 9, 30)


def test_load_cached_when_fetch_fails():
    S.write_cache(0.0372, date(2026, 9, 21), S.FRED_SOURCE, S.CACHE_PATH)
    q = S.load_sonia(TODAY)  # conftest makes the fetch fail
    assert (q.status, q.rate, q.source) == ("cached", pytest.approx(0.0372), S.FRED_SOURCE)
    assert q.age_days == 12 and q.business_days_old == 10  # Mon 21 Sep to Fri 2 Oct
    assert q.stale


def test_load_fallback_when_fetch_fails_and_no_cache():
    q = S.load_sonia(TODAY)
    assert (q.status, q.rate, q.source) == ("fallback", A.SONIA, S.PLACEHOLDER_SOURCE)
    assert q.as_of is None and q.age_days is None
    assert q.stale


def test_live_but_old_is_stale(monkeypatch):
    # 2026-09-21 (Mon) to 2026-10-03 (Sat): 10 weekdays -> more than 5
    monkeypatch.setattr(S, "fetch_latest_sonia",
                        lambda **kw: (0.0373, date(2026, 9, 21), S.BOE_SOURCE))
    q = S.load_sonia(TODAY)
    assert q.status == "live" and q.business_days_old == 10 and q.stale
    monkeypatch.setattr(S, "fetch_latest_sonia",
                        lambda **kw: (0.0373, TODAY - timedelta(days=7), S.BOE_SOURCE))
    # Sat 26 Sep: weekdays Mon 28 Sep to Fri 2 Oct = 5 -> not stale (limit is more than 5)
    assert S.load_sonia(TODAY).business_days_old == 5 and not S.load_sonia(TODAY).stale
