"""Descriptive statistics for any time series at its own published frequency.

Definitions (hand-checked in tests/test_series_stats.py):
- change: observation-to-observation difference at the series' own frequency (a weekly series
  gives week-on-week changes; no daily statistic is ever computed for weekly or monthly data)
- sd: sample standard deviation (ddof=1)
- change_z: (latest change - mean of all changes) / sd of all changes, over the window given
- level_pct: percentile rank of the latest level = share of observations <= latest, x 100
- level_z: (latest level - mean level) / sd of level
- bands: mean +/- 1 and 2 sd of the level over the window
Combining two series (spreads, slopes) only uses dates present in both: nothing is filled.
"""

import numpy as np
import pandas as pd

PERIOD_NOUN = {"daily": "day", "weekly": "week", "monthly": "month"}


def combine(a: pd.Series, b: pd.Series, scale: float = 1.0) -> pd.Series:
    """(a - b) x scale on dates where both have a value. No filling or interpolation."""
    joined = pd.concat({"a": a, "b": b}, axis=1, join="inner").dropna()
    return (joined["a"] - joined["b"]) * scale


def window(s: pd.Series, start) -> pd.Series:
    return s if start is None else s[s.index >= pd.Timestamp(start)]


def series_stats(s: pd.Series, frequency: str) -> dict:
    s = s.dropna()
    if len(s) < 3:
        raise ValueError("need at least 3 observations")
    ch = s.diff().dropna()
    last = float(s.iloc[-1])
    sd = float(s.std(ddof=1))
    ch_sd = float(ch.std(ddof=1))
    return {
        "n": int(len(s)),
        "frequency": frequency,
        "period": PERIOD_NOUN[frequency],
        "first_date": s.index[0].date(),
        "as_of": s.index[-1].date(),
        "last": last,
        "min": float(s.min()),
        "max": float(s.max()),
        "mean": float(s.mean()),
        "sd": sd,
        "change": float(ch.iloc[-1]),
        "change_z": float((ch.iloc[-1] - ch.mean()) / ch_sd) if ch_sd > 0 else float("nan"),
        "level_pct": float((s <= last).mean() * 100),
        "level_z": float((last - s.mean()) / sd) if sd > 0 else float("nan"),
    }


def bands(s: pd.Series) -> dict:
    m, sd = float(s.mean()), float(s.std(ddof=1))
    return {"mean": m, "+1sd": m + sd, "-1sd": m - sd, "+2sd": m + 2 * sd, "-2sd": m - 2 * sd}


def is_stretched(z: float, threshold: float = 2.0) -> bool:
    return bool(np.isfinite(z) and abs(z) > threshold)
