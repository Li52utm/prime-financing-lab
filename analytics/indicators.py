"""Technical indicators for the Markets page. Vectorised pandas; display analytics only.

Conventions (stated so the tests can hand-check them):
- Bollinger: middle = simple moving average; band = middle +/- width x rolling standard
  deviation with ddof=0 (population), as in Bollinger's definition.
- RSI: Wilder's method. The first average gain/loss is the simple mean of the first n
  changes; after that avg_t = (avg_{t-1} x (n - 1) + x_t) / n. RSI = 100 - 100 / (1 + RS),
  and 100 when the average loss is zero.
- Changes: prices use log returns; yields use differences in basis points.
- Realised volatility: rolling standard deviation (ddof=1) of daily changes x sqrt(252).
- Drawdown: prices close / running max - 1; yields close - running max, in bp.
"""

import numpy as np
import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window, min_periods=window).mean()


def bollinger(close: pd.Series, window: int = 20, width: float = 2.0) -> pd.DataFrame:
    mid = sma(close, window)
    sd = close.rolling(window, min_periods=window).std(ddof=0)
    upper, lower = mid + width * sd, mid - width * sd
    span = upper - lower
    pct_b = ((close - lower) / span).where(span > 0)
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower, "pct_b": pct_b})


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain, loss = delta.clip(lower=0.0), (-delta).clip(lower=0.0)
    out = pd.Series(np.nan, index=close.index)
    if len(close) <= window:
        return out
    g, l = gain.to_numpy(), loss.to_numpy()
    avg_g, avg_l = np.empty(len(g)), np.empty(len(g))
    avg_g[:] = np.nan
    avg_l[:] = np.nan
    avg_g[window] = g[1:window + 1].mean()
    avg_l[window] = l[1:window + 1].mean()
    # Wilder smoothing is an EMA with alpha = 1/n seeded at the simple mean
    a = 1.0 / window
    seeded_g = pd.Series(np.r_[avg_g[window], g[window + 1:]])
    seeded_l = pd.Series(np.r_[avg_l[window], l[window + 1:]])
    avg_g[window:] = seeded_g.ewm(alpha=a, adjust=False).mean().to_numpy()
    avg_l[window:] = seeded_l.ewm(alpha=a, adjust=False).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_g / avg_l
        values = np.where(avg_l == 0, 100.0, 100.0 - 100.0 / (1.0 + rs))
    out[:] = np.where(np.isnan(avg_g), np.nan, values)
    return out


def changes(close: pd.Series, is_yield: bool) -> pd.Series:
    """Daily changes: log returns for prices, bp differences for yields."""
    return close.diff() * 100.0 if is_yield else np.log(close).diff()


def realised_vol(close: pd.Series, is_yield: bool, window: int = 20,
                 trading_days: int = 252) -> pd.Series:
    """Annualised: a decimal for prices (0.15 = 15%), bp per year for yields."""
    return changes(close, is_yield).rolling(window, min_periods=window).std(ddof=1) * np.sqrt(
        trading_days)


def drawdown(close: pd.Series, is_yield: bool) -> pd.Series:
    peak = close.cummax()
    return (close - peak) * 100.0 if is_yield else close / peak - 1.0


def breaches(close: pd.Series, bands: pd.DataFrame) -> pd.Series:
    """+1 closing above the upper band, -1 below the lower band, 0 inside (NaN bands -> 0)."""
    above = (close > bands["upper"]).astype(int)
    below = (close < bands["lower"]).astype(int)
    return above - below


def breach_events(state: pd.Series) -> pd.Series:
    """First day of each breach: the state moves from inside (or the other side) to outside."""
    return state.where((state != 0) & (state != state.shift(1)), 0)


def forward_change(close: pd.Series, horizon: int, is_yield: bool) -> pd.Series:
    """Change over the next `horizon` rows: simple return for prices, bp for yields."""
    future = close.shift(-horizon)
    return (future - close) * 100.0 if is_yield else future / close - 1.0


def breach_study(close: pd.Series, bands: pd.DataFrame, horizons=(5, 20),
                 is_yield: bool = False) -> pd.DataFrame:
    """Frequency of closes outside the bands, and the average change after a breach event
    (first day outside) over each horizon, next to the unconditional average for scale."""
    state = breaches(close, bands)
    valid = bands["upper"].notna()
    events = breach_events(state)
    rows = []
    for side, label in ((1, "Above upper band"), (-1, "Below lower band")):
        row = {"side": label,
               "days_outside_pct": float((state[valid] == side).mean() * 100) if valid.any()
               else float("nan"),
               "events": int((events == side).sum())}
        for h in horizons:
            fwd = forward_change(close, h, is_yield)
            after = fwd[events == side].dropna()
            row[f"avg_next_{h}d"] = float(after.mean()) if len(after) else float("nan")
            row[f"n_next_{h}d"] = int(len(after))
            row[f"all_days_next_{h}d"] = float(fwd[valid].dropna().mean())
        rows.append(row)
    return pd.DataFrame(rows)


def summary_stats(close: pd.Series, bands: pd.DataFrame, is_yield: bool,
                  trading_days: int = 252) -> dict:
    """Last, daily change, 1Y change, 1Y volatility, max drawdown, position in the bands.
    1Y uses the last close on or before (last date - 365 days)."""
    last, prev = float(close.iloc[-1]), float(close.iloc[-2])
    one_year_ago = close[close.index <= close.index[-1] - pd.Timedelta(days=365)]
    base = float(one_year_ago.iloc[-1]) if len(one_year_ago) else float("nan")
    window = close[close.index > close.index[-1] - pd.Timedelta(days=365)]
    ch = changes(window, is_yield).dropna()
    return {
        "last": last,
        "daily_change": (last - prev) * 100.0 if is_yield else last / prev - 1.0,
        "one_year_change": (last - base) * 100.0 if is_yield else last / base - 1.0,
        "one_year_vol": float(ch.std(ddof=1) * np.sqrt(trading_days)) if len(ch) > 1
        else float("nan"),
        "max_drawdown": float(drawdown(close, is_yield).min()),
        "pct_b": float(bands["pct_b"].iloc[-1]),
    }
