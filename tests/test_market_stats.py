"""Correlation, rolling beta, regime classification, tails and seasonality against hand-worked
numbers."""

import math

import numpy as np
import pandas as pd
import pytest

from analytics import market_stats as MS


def ser(values, start="2026-01-05", freq="B"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq=freq), dtype=float)


def test_aligned_changes_uses_common_dates_only():
    """A (yield) on Mon-Thu, B (price) on Mon, Tue, Thu. Common dates Mon, Tue, Thu:
    A 1.00, 1.10, 1.30 -> bp changes +10, +20 (Tue->Thu spans the gap, nothing filled).
    B 100, 110, 121 -> log returns ln 1.1 twice."""
    a = ser([1.0, 1.1, 1.2, 1.3])
    b = pd.Series([100.0, 110.0, 121.0], index=a.index[[0, 1, 3]])
    ch = MS.aligned_changes({"a": a, "b": b}, {"a": True, "b": False})
    assert list(ch.index) == list(a.index[[1, 3]])
    assert ch["a"].tolist() == pytest.approx([10.0, 20.0])
    assert ch["b"].tolist() == pytest.approx([math.log(1.1)] * 2)


def test_rolling_corr_and_beta_hand_worked():
    """b = 1, 2, 3; a = 2b exactly -> corr 1, beta 2. Next window b = 2, 3, 1 and a = 4, 6, 5:
    mean b 2, mean a 5; cov = ((0)(-1) + (1)(1) + (-1)(0)) / 2 = 0.5; var b = (0+1+1)/2 = 1;
    beta 0.5; corr = 0.5 / (1 x 1) = 0.5 (var a = (1+1+0)/2 = 1)."""
    b = ser([1, 2, 3, 1])
    a = ser([2, 4, 6, 5])
    rc = MS.rolling_corr_beta(a, b, 3)
    assert rc["corr"].iloc[2] == pytest.approx(1.0) and rc["beta"].iloc[2] == pytest.approx(2.0)
    assert rc["corr"].iloc[3] == pytest.approx(0.5) and rc["beta"].iloc[3] == pytest.approx(0.5)


def test_corr_matrix_windows_and_min_obs():
    """Prices doubling/halving alternately: log returns +ln2, -ln2 ... for x; y the mirror image
    -> correlation -1. With min_obs above the common count the cell is NaN."""
    x = ser([1, 2, 1, 2, 1, 2])
    y_ = ser([2, 1, 2, 1, 2, 1])
    corr, n = MS.corr_matrix({"x": x, "y": y_}, {"x": False, "y": False}, None, 3)
    assert corr.loc["x", "y"] == pytest.approx(-1.0) and n.loc["x", "y"] == 5
    corr, n = MS.corr_matrix({"x": x, "y": y_}, {"x": False, "y": False}, 3, 4)
    assert n.loc["x", "y"] == 3 and np.isnan(corr.loc["x", "y"])
    assert corr.loc["x", "x"] == 1.0


def test_regimes_and_table():
    """Vol 1..8: 25th pct = 1 + 0.25 x 7 = 2.75, 75th = 1 + 0.75 x 7 = 6.25 (linear).
    Low: 1, 2; high: 7, 8; normal: 3..6. Changes: low days +1, +3 (mean 2, sd 1.414214);
    normal days 0 x 4; high days -2, -4 (mean -3). Shares 25 / 50 / 25 %."""
    vol = ser([np.nan, 1, 2, 3, 4, 5, 6, 7, 8])
    lab, lo, hi = MS.regimes(vol, 25, 75)
    assert (lo, hi) == pytest.approx((2.75, 6.25))
    assert lab.tolist() == ["low"] * 2 + ["normal"] * 4 + ["high"] * 2
    ch = pd.Series([1, 3, 0, 0, 0, 0, -2, -4], index=lab.index, dtype=float)
    t = MS.regime_table(lab, ch).set_index("regime")
    assert t.loc["low", "mean"] == pytest.approx(2.0) and t.loc["low", "sd"] == pytest.approx(math.sqrt(2))
    assert t.loc["high", "mean"] == pytest.approx(-3.0)
    assert t["share"].tolist() == pytest.approx([25.0, 50.0, 25.0]) and t["days"].sum() == 8
    assert [r for *_, r in MS.runs(lab)] == ["low", "normal", "high"]


def test_tails_and_tail_counts():
    """1..100: mean 50.5, sample sd 29.011492. Empirical 5th pct (linear) = 1 + 0.05 x 99 = 5.95;
    normal 5th = 50.5 - 1.644854 x 29.011492 = 2.781. No value is beyond 3 SD; a normal expects
    100 x 0.0026998 = 0.27."""
    x = pd.Series(np.arange(1, 101, dtype=float))
    t = MS.tails(x, (5, 95)).set_index("percentile")
    assert t.loc[5, "empirical"] == pytest.approx(5.95)
    assert t.loc[5, "normal"] == pytest.approx(50.5 - 1.6448536 * 29.0114920, abs=1e-4)
    c = MS.tail_counts(x)
    assert c["observed"] == 0 and c["expected"] == pytest.approx(0.26998, abs=1e-4)
    assert c["skew"] == pytest.approx(0.0, abs=1e-12)


def test_monthly_changes_and_seasonality():
    """Month-ends 100 (Jan), 110 (Feb), 99 (Mar), 99 (Apr): returns Feb +10%, Mar -10%, Apr 0%.
    The running month (May, contains 'today') is dropped. Yields: bp changes."""
    idx = pd.to_datetime(["2025-01-31", "2025-02-28", "2025-03-31", "2025-04-30", "2025-05-15"])
    s = pd.Series([100, 110, 99, 99, 120], index=idx, dtype=float)
    m = MS.monthly_changes(s, False, today="2025-05-20")
    assert m.tolist() == pytest.approx([10.0, -10.0, 0.0])
    my = MS.monthly_changes(pd.Series([1.0, 1.25, 1.2, 1.2, 9.0], index=idx), True, today="2025-05-20")
    assert my.tolist() == pytest.approx([25.0, -5.0, 0.0])
    sea = MS.seasonality(m, min_n=2)
    assert sea.loc[2, "mean"] == pytest.approx(10.0) and sea.loc[2, "n"] == 1
    assert sea.loc[2, "pct_up"] == 100.0 and sea.loc[4, "pct_up"] == 0.0
    assert bool(sea.loc[2, "small_sample"]) and sea.loc[6, "n"] == 0
