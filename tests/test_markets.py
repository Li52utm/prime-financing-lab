"""Offline tests for data/markets.py and analytics/indicators.py. No test touches the network."""

import math
import time

import numpy as np
import pandas as pd
import pytest

from analytics import indicators as I
from data import markets as M

approx = pytest.approx
REAL_FETCH = M.fetch_live  # captured before conftest replaces it with a failing stub


# --- Parsers (samples in the formats verified on 2026-10-03) -------------------------------------

def test_parse_boe_csv():
    text = "DATE,IUDMNPY\n29 Sep 2026,5.364\n30 Sep 2026,5.3714\n"
    df = M.parse_boe_csv(text, "IUDMNPY")
    assert list(df.index.strftime("%Y-%m-%d")) == ["2026-09-29", "2026-09-30"]
    assert df["close"].tolist() == approx([5.364, 5.3714])
    with pytest.raises(ValueError):
        M.parse_boe_csv("<!DOCTYPE html>", "IUDMNPY")  # BoE error page (e.g. date before 1963)


def test_parse_bundesbank_csv_skips_metadata_and_missing():
    text = ('﻿"",BBSIS.D.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A,FLAGS\n'
            '"",Term structure ... residual maturity of 10.0 years / daily data,\n'
            "Decimals,2,\nunit,Prozent,\nlast update,2026-10-01 12:45:17,\n"
            "2026-09-26,.,No value available\n2026-09-29,3.62,\n2026-09-30,3.64,\n"
            "2026-10-01,3.66,\n")
    df = M.parse_bundesbank_csv(text)
    assert list(df.index.strftime("%Y-%m-%d")) == ["2026-09-29", "2026-09-30", "2026-10-01"]
    assert df["close"].iloc[-1] == approx(3.66)


def test_eia_frame():
    raw = pd.DataFrame({"Date": pd.to_datetime(["1987-05-20", "1987-05-21", None]),
                        "Europe Brent Spot Price FOB (Dollars per Barrel)": [18.63, 18.45, None]})
    df = M.eia_frame(raw)
    assert len(df) == 2 and df["close"].tolist() == approx([18.63, 18.45])


def test_normalise_yahoo():
    idx = pd.DatetimeIndex(["2026-10-01 00:00:00+01:00", "2026-10-02 00:00:00+01:00"])
    raw = pd.DataFrame({"Open": [10606.4, 10428.2], "High": [10606.4, 10503.2],
                        "Low": [10390.7, 10413.4], "Close": [10428.3, 10462.0],
                        "Adj Close": [10428.3, 10462.0], "Volume": [0, 689426700]}, index=idx)
    df = M.normalise_yahoo(raw)
    assert df.index.tz is None
    assert list(df.index.strftime("%Y-%m-%d")) == ["2026-10-01", "2026-10-02"]
    assert math.isnan(df["volume"].iloc[0]) and df["volume"].iloc[1] == 689426700
    with pytest.raises(ValueError):
        M.normalise_yahoo(pd.DataFrame())


def test_sanity_check():
    good = pd.DataFrame({"close": np.linspace(3.0, 4.0, 40)},
                        index=pd.bdate_range("2026-01-01", periods=40))
    assert M.sanity_check(good, M.SERIES["uk10y"]) is good
    with pytest.raises(ValueError):
        M.sanity_check(good.iloc[:10], M.SERIES["uk10y"])  # too short
    with pytest.raises(ValueError):
        M.sanity_check(good * 20, M.SERIES["uk10y"])  # 60-80% is not a yield
    with pytest.raises(ValueError):
        M.sanity_check(good - 10, M.SERIES["spx"])  # negative index


# --- Load order: live -> cache -> error ------------------------------------------------------

def frame(n=60, start=100.0):
    idx = pd.bdate_range("2026-06-01", periods=n)
    return pd.DataFrame({"close": start + np.arange(n, dtype=float)}, index=idx)


def test_load_live_writes_cache(monkeypatch):
    monkeypatch.setattr(M, "fetch_live", lambda key: frame())
    s = M.load_series("brent")
    assert s.status == "live" and s.as_of == frame().index[-1].date()
    assert "Source: EIA" in s.stamp and "status live" in s.stamp
    cached, fetched_at = M.read_cache("brent")
    assert cached["close"].tolist() == approx(frame()["close"].tolist()) and fetched_at


def test_load_cached_when_fetch_fails():
    M.write_cache("gbpusd", frame(start=1.2) / 100 * 100, "2026-10-01T09:00:00")
    s = M.load_series("gbpusd")  # conftest: live fetch fails
    assert s.status == "cached" and s.fetched_at == "2026-10-01T09:00:00"
    assert "status cached" in s.stamp


def test_load_error_when_fetch_fails_and_no_cache():
    with pytest.raises(M.MarketDataError, match="no cached copy"):
        M.load_series("spx")


def test_load_error_on_corrupt_cache():
    M.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (M.CACHE_DIR / "ftse100.csv").write_text("not,a,frame\n")
    (M.CACHE_DIR / "ftse100.meta.json").write_text("{")
    with pytest.raises(M.MarketDataError):
        M.load_series("ftse100")


def test_fetch_live_dispatch_parses_each_provider(monkeypatch):
    """The real fetch_live with the network stubs replaced by verified-format samples."""
    boe = "DATE,{code}\n" + "\n".join(f"{d:%d %b %Y},1.25" for d in frame().index)
    bbk = "﻿header\n" + "\n".join(f"{d:%Y-%m-%d},3.1," for d in frame().index)
    monkeypatch.setattr(M, "_get", lambda url, binary=False: (
        boe.replace("{code}", "XUDLUSS" if "XUDLUSS" in url else "IUDMNPY")
        if "bankofengland" in url else bbk))
    monkeypatch.setattr(M, "_yahoo_history", lambda sym: frame().rename(columns={"close": "Close"})
                        .assign(Open=1.0, High=2.0, Low=0.5, Volume=10))
    assert REAL_FETCH("gbpusd")["close"].iloc[-1] == approx(1.25)
    assert REAL_FETCH("uk10y")["close"].iloc[0] == approx(1.25)
    assert REAL_FETCH("bund10y")["close"].iloc[-1] == approx(3.1)
    assert set(REAL_FETCH("spx").columns) == {"open", "high", "low", "close", "volume"}


# --- Indicators: hand-worked -----------------------------------------------------------------

def test_bollinger_hand_worked():
    """close 1..5, window 3, width 2 (population std):
    at index 2: mean 2, var ((1-2)^2 + 0 + (3-2)^2) / 3 = 2/3, sd 0.816497
      upper = 2 + 2 x 0.816497 = 3.632993, lower = 0.367007
      %b = (3 - 0.367007) / (3.632993 - 0.367007) = 2.632993 / 3.265986 = 0.806186
    """
    b = I.bollinger(pd.Series([1.0, 2, 3, 4, 5]), 3, 2.0)
    assert b["mid"].iloc[:2].isna().all()
    assert b.loc[2, ["mid", "upper", "lower"]].tolist() == approx([2.0, 3.632993, 0.367007])
    assert b.loc[4, "upper"] == approx(5.632993)
    assert b.loc[2, "pct_b"] == approx(0.806186)


def test_bollinger_flat_series_pct_b_undefined():
    b = I.bollinger(pd.Series([5.0] * 6), 3, 2.0)
    assert b["upper"].iloc[-1] == b["lower"].iloc[-1] == 5.0
    assert b["pct_b"].isna().all()


def test_rsi_wilder_hand_worked():
    """close 10, 11, 10.5, 11.5, 12, 11; window 3. Changes +1, -0.5, +1, +0.5, -1.
    t=3: avg gain (1 + 0 + 1)/3 = 0.666667, avg loss 0.5/3 = 0.166667, RS 4 -> RSI 80
    t=4: gain (0.666667 x 2 + 0.5)/3 = 0.611111, loss (0.166667 x 2)/3 = 0.111111,
         RS 5.5 -> RSI 100 - 100/6.5 = 84.615385
    t=5: gain (0.611111 x 2)/3 = 0.407407, loss (0.111111 x 2 + 1)/3 = 0.407407 -> RSI 50
    """
    r = I.rsi(pd.Series([10, 11, 10.5, 11.5, 12, 11.0]), 3)
    assert r.iloc[:3].isna().all()
    assert r.iloc[3:].tolist() == approx([80.0, 84.615385, 50.0])


def test_rsi_all_gains_is_100_and_short_series_nan():
    assert I.rsi(pd.Series([1.0, 2, 3, 4, 5]), 3).iloc[-1] == 100.0
    assert I.rsi(pd.Series([1.0, 2]), 3).isna().all()


def test_drawdown_hand_worked():
    """prices 100, 110, 99, 121, 108.9: peaks 100, 110, 110, 121, 121
    -> 0, 0, 99/110 - 1 = -10%, 0, 108.9/121 - 1 = -10%.
    yields 4.0, 4.5, 4.2, 4.6: peaks 4.0, 4.5, 4.5, 4.6 -> 0, 0, -30 bp, 0."""
    assert I.drawdown(pd.Series([100, 110, 99, 121, 108.9]), False).tolist() == approx(
        [0, 0, -0.1, 0, -0.1])
    assert I.drawdown(pd.Series([4.0, 4.5, 4.2, 4.6]), True).tolist() == approx([0, 0, -30, 0])


def test_realised_vol_hand_worked():
    """yields 1.00, 1.10, 1.00, 1.10 -> changes +10, -10, +10 bp; window 2, ddof 1:
    std(10, -10) = 14.142136; x sqrt(252) = 224.4994 bp/yr. A constant-growth price -> 0."""
    v = I.realised_vol(pd.Series([1.0, 1.1, 1.0, 1.1]), True, 2)
    assert v.iloc[2:].tolist() == approx([224.4994, 224.4994])
    assert I.realised_vol(pd.Series(100 * 1.01 ** np.arange(10)), False, 3).iloc[-1] == approx(0, abs=1e-12)


def test_breaches_and_events():
    close = pd.Series([10, 12, 13, 9, 8, 10.0])
    bands = pd.DataFrame({"upper": [11] * 6, "lower": [9.5] * 6})
    state = I.breaches(close, bands)
    assert state.tolist() == [0, 1, 1, -1, -1, 0]
    assert I.breach_events(state).tolist() == [0, 1, 0, -1, 0, 0]


def test_breach_study_hand_worked():
    """close 10, 12, 13, 9, 8, 10, bands 11 / 9.5 on every day (all valid).
    Days outside: above 2/6 = 33.33%, below 2/6 = 33.33%. Events: above at t=1, below at t=3.
    Forward 1-day simple return: t=1 13/12 - 1 = 8.3333%; t=3 8/9 - 1 = -11.1111%.
    All days (t=0..4): 20%, 8.3333%, -30.7692%, -11.1111%, 25% -> mean 2.2906%."""
    close = pd.Series([10, 12, 13, 9, 8, 10.0])
    bands = pd.DataFrame({"upper": [11.0] * 6, "lower": [9.5] * 6})
    s = I.breach_study(close, bands, horizons=(1,)).set_index("side")
    assert s.loc["Above upper band", "days_outside_pct"] == approx(100 / 3)
    assert s.loc["Above upper band", "events"] == 1
    assert s.loc["Above upper band", "avg_next_1d"] == approx(13 / 12 - 1)
    assert s.loc["Below lower band", "avg_next_1d"] == approx(8 / 9 - 1)
    assert s.loc["Below lower band", "all_days_next_1d"] == approx(0.022906, abs=1e-6)


def test_summary_stats_hand_worked():
    """Daily closes on calendar days: 100 for a year, then 110, 121 on the last two days.
    Last 121; daily change 121/110 - 1 = 10%; one year back is 100 -> +21%;
    max drawdown 0 (never below a peak)."""
    idx = pd.date_range("2025-01-01", periods=368, freq="D")
    close = pd.Series([100.0] * 366 + [110.0, 121.0], index=idx)
    bands = I.bollinger(close, 3, 2.0)
    s = I.summary_stats(close, bands, False)
    assert s["last"] == 121 and s["daily_change"] == approx(0.10)
    assert s["one_year_change"] == approx(0.21) and s["max_drawdown"] == 0
    y = I.summary_stats(close / 100 * 4, I.bollinger(close / 100 * 4, 3, 2.0), True)
    assert y["daily_change"] == approx(44.0)  # 4.84% - 4.40% = 44 bp


def test_indicators_fast_on_20_years():
    """20 years of business days (~5,200 rows): every indicator well under a second."""
    rng = np.random.default_rng(7)
    idx = pd.bdate_range("2006-01-02", periods=20 * 261)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx)))), index=idx)
    t = time.perf_counter()
    bands = I.bollinger(close, 20, 2.0)
    I.sma(close, 50), I.sma(close, 200), I.rsi(close, 14), I.realised_vol(close, False)
    I.drawdown(close, False), I.breach_study(close, bands, (5, 20)), I.summary_stats(close, bands, False)
    assert time.perf_counter() - t < 0.5
