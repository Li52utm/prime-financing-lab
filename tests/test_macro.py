"""Offline tests for data/macro.py (rates, liquidity, FX). No test touches the network."""

import json
import pathlib
from datetime import date

import pandas as pd
import pytest

from data import macro as M

approx = pytest.approx
REAL_FETCH = M.fetch_live  # conftest replaces the module attribute with a failing stub
REAL_FETCH_UST = M._fetch_ust


def test_parse_ecb_daily_monthly_weekly():
    daily = ("KEY,FREQ,TIME_PERIOD,OBS_VALUE\nYC.B.U2...SR_2Y,B,2026-09-30,3.1591707336\n"
             "YC.B.U2...SR_2Y,B,2026-10-01,3.1064811134\n")
    s = M.parse_ecb_csv(daily)
    assert list(s.index.strftime("%Y-%m-%d")) == ["2026-09-30", "2026-10-01"]
    assert s.iloc[-1] == approx(3.1064811134)
    monthly = "KEY,TIME_PERIOD,OBS_VALUE\nIRS.M.IT,2026-07,3.881\nIRS.M.IT,2026-08,3.986\n"
    assert list(M.parse_ecb_csv(monthly).index.strftime("%Y-%m-%d")) == ["2026-07-01", "2026-08-01"]
    weekly = "KEY,TIME_PERIOD,OBS_VALUE\nILM.W,2026-W39,1956554\n"
    assert M.parse_ecb_csv(weekly).index[0].date() == date(2026, 9, 21)  # Monday of ISO week 39
    with pytest.raises(ValueError):
        M.parse_ecb_csv("<html>error</html>")


def test_parse_ecb_skips_blank_values():
    text = "KEY,TIME_PERIOD,OBS_VALUE\nK,2026-09-29,\nK,2026-09-30,2.437\n"
    assert len(M.parse_ecb_csv(text)) == 1


def test_parse_ust_csv_newest_first():
    text = ('Date,"1 Mo","2 Yr","10 Yr"\n10/02/2026,4.04,4.83,5.28\n10/01/2026,4.06,4.78,5.24\n')
    s = M.parse_ust_csv(text, "2 Yr")
    assert list(s.index.strftime("%Y-%m-%d")) == ["2026-10-01", "2026-10-02"]  # sorted ascending
    assert s.tolist() == approx([4.78, 4.83])
    with pytest.raises(ValueError):
        M.parse_ust_csv(text, "7 Yr")


def test_ust_incremental_merge(monkeypatch):
    """With a cache, only the last two years are refetched and newer values win."""
    calls = []
    def fake_get(url, *a, **k):
        year = int(url.split("daily-treasury-rates.csv/")[1].split("/")[0])
        calls.append(year)
        return f'Date,"2 Yr"\n01/05/{year},{year - 2000}.5\n'
    monkeypatch.setattr(M, "_get", fake_get)
    cached = pd.Series([1.0, 2.0], index=pd.to_datetime(["2020-01-06", "2025-01-05"]))
    s = REAL_FETCH_UST("2 Yr", cached, today=date(2026, 10, 4))
    assert calls == [2025, 2026]
    assert s.loc["2025-01-05"] == approx(25.5) and s.loc["2020-01-06"] == 1.0
    calls.clear()
    REAL_FETCH_UST("2 Yr", None, today=date(1991, 3, 1))
    assert calls == [1990, 1991]  # no cache: every year from 1990


def test_sanity_check():
    s = pd.Series([3.0] * 20, index=pd.bdate_range("2026-01-01", periods=20))
    assert M.sanity_check(s, M.SERIES["uk_10y"]) is s
    with pytest.raises(ValueError):
        M.sanity_check(s * 20, M.SERIES["uk_10y"])
    with pytest.raises(ValueError):
        M.sanity_check(s.iloc[:5], M.SERIES["uk_10y"])


def test_real_fetch_dispatch_ecb_and_boe(monkeypatch):
    ecb = "KEY,TIME_PERIOD,OBS_VALUE\n" + "".join(f"K,2026-09-{d:02d},2.4\n" for d in range(1, 25))
    boe = "DATE,IUDBEDR\n" + "".join(f"{d:02d} Sep 2026,3.75\n" for d in range(1, 25))
    monkeypatch.setattr(M, "_get", lambda url, *a, **k: ecb if "ecb.europa.eu" in url else boe)
    assert REAL_FETCH("estr").iloc[-1] == approx(2.4)
    assert REAL_FETCH("boe_bank_rate").iloc[0] == approx(3.75)


def test_load_order_live_cache_error(monkeypatch):
    s = pd.Series([3.0 + i / 100 for i in range(30)], index=pd.bdate_range("2026-08-01", periods=30))
    with pytest.raises(M.MacroDataError, match="no cached copy"):
        M.load_macro("uk_10y")  # conftest: live fails, empty cache
    monkeypatch.setattr(M, "fetch_live", lambda key: s)
    live = M.load_macro("uk_10y")
    assert live.status == "live" and "daily" in live.stamp and "status live" in live.stamp
    monkeypatch.setattr(M, "fetch_live", lambda key: (_ for _ in ()).throw(ConnectionError("down")))
    cached = M.load_macro("uk_10y")
    assert cached.status == "cached" and cached.data.tolist() == approx(s.tolist())


def test_every_series_has_terms_frequency_and_audited_earliest_date():
    audit_path = pathlib.Path(M.__file__).resolve().parent / "source_audit.json"
    audit = {r["key"]: r for r in json.loads(audit_path.read_text(encoding="utf-8"))["series"]}
    for key, spec in M.SERIES.items():
        assert spec.frequency in ("daily", "weekly", "monthly")
        assert M.terms_for(spec)
        assert audit[key]["works"] and audit[key]["earliest"].startswith(spec.earliest_verified[:7])
    assert "Terms unverified" in M.terms_for(M.SERIES["us_2y"])
