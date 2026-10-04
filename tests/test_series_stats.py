"""Hand-worked tests for analytics/series_stats.py."""

import math

import pandas as pd
import pytest

from analytics import series_stats as S

approx = pytest.approx


def weekly(values):
    return pd.Series(values, index=pd.date_range("2026-01-07", periods=len(values), freq="7D"))


def test_series_stats_hand_worked():
    """levels 1, 2, 3, 4, 10 (weekly). mean 4, sample var ((-3)^2+(-2)^2+1+0+36)/4 = 50/4 = 12.5
    sd 3.535534. changes 1, 1, 1, 6: mean 2.25, sample sd sqrt(((-1.25)^2*3 + 3.75^2)/3)
    = sqrt((4.6875 + 14.0625)/3) = sqrt(6.25) = 2.5 -> change_z = (6 - 2.25)/2.5 = 1.5
    level_pct: 5 of 5 values <= 10 -> 100. level_z = (10 - 4)/3.535534 = 1.697056"""
    st = S.series_stats(weekly([1.0, 2, 3, 4, 10]), "weekly")
    assert st["period"] == "week" and st["n"] == 5
    assert (st["min"], st["max"], st["mean"]) == (1, 10, 4)
    assert st["sd"] == approx(3.535534)
    assert st["change"] == 6 and st["change_z"] == approx(1.5)
    assert st["level_pct"] == 100 and st["level_z"] == approx(1.697056)


def test_percentile_counts_ties_inclusive():
    """levels 5, 1, 5, 3: latest 3 -> values <= 3 are 1 and 3 -> 2 of 4 = 50%"""
    assert S.series_stats(weekly([5.0, 1, 5, 3]), "weekly")["level_pct"] == 50


def test_constant_changes_give_nan_z():
    st = S.series_stats(weekly([1.0, 2, 3, 4]), "weekly")
    assert math.isnan(st["change_z"])


def test_bands():
    """levels 1, 2, 3, 4, 10: mean 4, sd 3.535534"""
    b = S.bands(weekly([1.0, 2, 3, 4, 10]))
    assert b["+1sd"] == approx(7.535534) and b["-2sd"] == approx(-3.071068)


def test_combine_inner_join_no_fill():
    a = pd.Series([3.0, 3.2, 3.4], index=pd.to_datetime(["2026-09-28", "2026-09-29", "2026-09-30"]))
    b = pd.Series([2.0, 2.5], index=pd.to_datetime(["2026-09-28", "2026-09-30"]))
    s = S.combine(a, b, 100)
    assert list(s.index.strftime("%Y-%m-%d")) == ["2026-09-28", "2026-09-30"]  # 29th dropped
    assert s.tolist() == approx([100.0, 90.0])


def test_window_and_stretched():
    s = weekly([1.0, 2, 3, 4, 10])
    assert len(S.window(s, "2026-01-21")) == 3 and len(S.window(s, None)) == 5
    assert S.is_stretched(2.01) and not S.is_stretched(-1.99) and not S.is_stretched(float("nan"))


def test_needs_three_points():
    with pytest.raises(ValueError):
        S.series_stats(weekly([1.0, 2]), "weekly")
