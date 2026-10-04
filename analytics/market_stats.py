"""Cross-asset and distribution statistics for the Markets page. Descriptive only: nothing here is
a forecast and nothing feeds the financing engine.

Conventions (hand-checked in tests/test_market_stats.py):
- Daily changes: log returns for prices, bp differences for yields (analytics.indicators.changes).
- Two series are aligned on dates where both have a close, and changes are taken on that joined
  calendar, so each change spans the same interval for both (no filling).
- Correlation: Pearson on aligned changes. Beta of A on B = cov(A, B) / var(B), sample moments.
- Regimes: rolling volatility classified by its percentile within the series' own history:
  below the low percentile = low, above the high percentile = high, otherwise normal.
- Tails: empirical percentiles of daily changes against a normal with the same mean and SD.
- Seasonality: month-end to month-end change, grouped by calendar month; the current partial month
  is excluded.
"""

from math import erf, sqrt
from statistics import NormalDist

import numpy as np
import pandas as pd

from analytics.indicators import changes


def aligned_changes(closes: dict[str, pd.Series], is_yield: dict[str, bool]) -> pd.DataFrame:
    """Changes for several series on the dates where all have a close."""
    joined = pd.concat(closes, axis=1, join="inner").dropna()
    return pd.DataFrame({k: changes(joined[k], is_yield[k]) for k in joined}).dropna()


def corr_matrix(closes: dict[str, pd.Series], is_yield: dict[str, bool], window: int | None,
                min_obs: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pairwise correlation over the last `window` common changes of each pair (each pair uses
    its own common calendar). Returns (correlation, observation counts); NaN below min_obs."""
    keys = list(closes)
    corr = pd.DataFrame(np.nan, index=keys, columns=keys)
    nobs = pd.DataFrame(0, index=keys, columns=keys)
    for i, a in enumerate(keys):
        for b in keys[i:]:
            if a == b:
                n = int(changes(closes[a].dropna(), is_yield[a]).dropna().shape[0])
                n = n if window is None else min(n, window)
                corr.loc[a, a], nobs.loc[a, a] = 1.0, n
                continue
            ch = aligned_changes({a: closes[a], b: closes[b]}, is_yield)
            if window is not None:
                ch = ch.iloc[-window:]
            n = len(ch)
            c = float(ch[a].corr(ch[b])) if n >= min_obs else np.nan
            corr.loc[a, b] = corr.loc[b, a] = c
            nobs.loc[a, b] = nobs.loc[b, a] = n
    return corr, nobs


def rolling_corr_beta(a: pd.Series, b: pd.Series, window: int) -> pd.DataFrame:
    """Rolling correlation of a with b and beta of a on b over `window` aligned changes."""
    df = pd.concat({"a": a, "b": b}, axis=1, sort=True).dropna()
    cov = df["a"].rolling(window).cov(df["b"])
    var = df["b"].rolling(window).var()
    return pd.DataFrame({"corr": df["a"].rolling(window).corr(df["b"]), "beta": cov / var})


def regimes(vol: pd.Series, low_pct: float, high_pct: float) -> tuple[pd.Series, float, float]:
    """Classify rolling vol as low / normal / high by its percentiles in the history given.
    Returns (labels, low threshold, high threshold). NaN vol stays unclassified."""
    v = vol.dropna()
    lo, hi = float(np.percentile(v, low_pct)), float(np.percentile(v, high_pct))
    lab = pd.Series(np.where(v < lo, "low", np.where(v > hi, "high", "normal")), index=v.index)
    return lab, lo, hi


def regime_table(labels: pd.Series, ch: pd.Series) -> pd.DataFrame:
    """Time in each regime and the mean same-day change on those days."""
    df = pd.concat({"r": labels, "c": ch}, axis=1, sort=True).dropna()
    rows = []
    for r in ("low", "normal", "high"):
        x = df.loc[df["r"] == r, "c"]
        rows.append({"regime": r, "days": int(len(x)),
                     "share": len(x) / len(df) * 100 if len(df) else np.nan,
                     "mean": float(x.mean()) if len(x) else np.nan,
                     "sd": float(x.std(ddof=1)) if len(x) > 1 else np.nan})
    return pd.DataFrame(rows)


def runs(labels: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp, str]]:
    """Contiguous stretches of the same label: (first date, last date, label)."""
    if labels.empty:
        return []
    block = (labels != labels.shift()).cumsum()
    return [(g.index[0], g.index[-1], g.iloc[0]) for _, g in labels.groupby(block)]


def tails(ch: pd.Series, pcts) -> pd.DataFrame:
    """Empirical percentiles (linear interpolation) against a normal with the same mean and SD."""
    x = ch.dropna()
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    nd = NormalDist(mu, sd)
    return pd.DataFrame({"percentile": list(pcts),
                         "empirical": [float(np.percentile(x, p)) for p in pcts],
                         "normal": [nd.inv_cdf(p / 100) for p in pcts]})


def tail_counts(ch: pd.Series, k: float = 3.0) -> dict:
    """Observed count of changes beyond mean +/- k SD against the count a normal would give."""
    x = ch.dropna()
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    p_beyond = 1 - erf(k / sqrt(2))  # two-sided normal tail probability
    return {"n": int(len(x)), "observed": int(((x - mu).abs() > k * sd).sum()),
            "expected": float(len(x) * p_beyond), "skew": float(x.skew()),
            "excess_kurtosis": float(x.kurt())}


def monthly_changes(close: pd.Series, is_yield: bool, today=None) -> pd.Series:
    """Month-end to month-end change (% simple return for prices, bp for yields). The month that
    contains `today` (default: the current date) is still running, so it is dropped."""
    me = close.dropna().resample("ME").last().dropna()
    today = pd.Timestamp.today() if today is None else pd.Timestamp(today)
    if len(me) and me.index[-1].to_period("M") == today.to_period("M"):
        me = me.iloc[:-1]
    out = me.diff() * 100 if is_yield else me.pct_change() * 100
    return out.dropna()


def seasonality(monthly: pd.Series, min_n: int) -> pd.DataFrame:
    g = monthly.groupby(monthly.index.month)
    df = pd.DataFrame({"mean": g.mean(), "median": g.median(), "n": g.size(),
                       "pct_up": g.apply(lambda s: (s > 0).mean() * 100),
                       "sd": g.std(ddof=1)}).reindex(range(1, 13))
    df["n"] = df["n"].fillna(0).astype(int)
    df["small_sample"] = df["n"] < min_n
    return df
