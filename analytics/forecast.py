"""Forecast Lab (EXPERIMENTAL): pure maths for the offline walk-forward test in
scripts/run_forecasts.py. The app never imports a fitting library or trains anything; it only
displays the saved results.

Conventions (hand-checked in tests/test_forecast.py):
- r_t is the daily log return from close t-1 to close t. A value "at t" uses closes up to t only.
- Targets at t look forward: realised variance RV_t = sum of r_{t+1..t+h}^2; forward return
  y_t = sum of r_{t+1..t+h}; direction = 1 if y_t > 0 else 0 (a zero return counts as not up).
- Walk-forward: the first prediction is made at row min_train; models are refitted every `refit`
  rows on an expanding window. At a refit made at row t, a training row s is used only if its
  target is fully observed by t, i.e. s + h <= t. Nothing after t is ever seen.
- Losses (lower is better). Volatility: QLIKE = ln F + RV / F (Patton 2011 form; differences
  between models equal those of RV/F - ln(RV/F) - 1, and RV = 0 is allowed) and MAE of the
  forecast volatility sqrt(F) against realised sqrt(RV). Returns: squared error. Direction:
  0-1 loss (1 = wrong call).
- Comparison: d_t = loss(model) - loss(naive) over the common test dates; the mean of d with a
  moving-block bootstrap percentile interval (blocks keep the autocorrelation that overlapping
  multi-day targets create).
- Verdict: "beats naive" if the whole interval is below 0, "does not beat naive" if the whole
  interval is above 0, otherwise "inconclusive".
"""

from typing import Callable

import numpy as np
import pandas as pd

BEATS, LOSES, INCONCLUSIVE = "beats naive", "does not beat naive", "inconclusive"


# --- Inputs and targets ----------------------------------------------------------------------

def log_returns(close: pd.Series) -> pd.Series:
    return np.log(close.astype(float)).diff().dropna()


def forward_sum(x: pd.Series, h: int) -> pd.Series:
    """Value at t = x_{t+1} + ... + x_{t+h}; NaN for the last h rows (not yet observed)."""
    return x[::-1].rolling(h).sum()[::-1].shift(-1)


def realised_forward(r: pd.Series, h: int) -> pd.Series:
    return forward_sum(r ** 2, h)


def forward_return(r: pd.Series, h: int) -> pd.Series:
    return forward_sum(r, h)


# --- Volatility forecasts (h-day variance, known at t) ---------------------------------------

def naive_variance(r: pd.Series, h: int) -> pd.Series:
    """Naive baseline: the last h days' realised variance carried forward."""
    return (r ** 2).rolling(h).sum()


def ewma_variance(r: pd.Series, lam: float, seed_n: int) -> pd.Series:
    """One-day-ahead EWMA variance at t: s2_{t+1} = lam * s2_t + (1 - lam) * r_t^2, seeded with the
    mean of the first seed_n squared returns (rows before seed_n are NaN: warm-up)."""
    x = r.to_numpy(dtype=float) ** 2
    out = np.full(len(x), np.nan)
    if len(x) <= seed_n:
        return pd.Series(out, index=r.index)
    s2 = x[:seed_n].mean()
    for t in range(len(x)):
        s2 = lam * s2 + (1 - lam) * x[t]
        if t >= seed_n:
            out[t] = s2
    return pd.Series(out, index=r.index)


def garch_next_variance(r: np.ndarray, omega: float, alpha: float, beta: float,
                        s0: float) -> np.ndarray:
    """One-day-ahead GARCH(1,1) variance at each t: s2_{t+1} = omega + alpha r_t^2 + beta s2_t,
    starting from s2_0 = s0."""
    out = np.empty(len(r))
    s2 = s0
    for t in range(len(r)):
        s2 = omega + alpha * r[t] ** 2 + beta * s2
        out[t] = s2
    return out


def garch_h_sum(next_var: np.ndarray | float, omega: float, alpha: float, beta: float,
                h: int) -> np.ndarray | float:
    """Sum of the 1..h step variance forecasts: sum_k [vbar + p^(k-1) (s2_{t+1} - vbar)] with
    p = alpha + beta and vbar = omega / (1 - p). If p >= 1 (no finite long-run variance) the
    recursion E[s2_{t+k}] = omega + p E[s2_{t+k-1}] is summed directly."""
    p = alpha + beta
    if p < 1:
        vbar = omega / (1 - p)
        return h * vbar + (next_var - vbar) * (1 - p ** h) / (1 - p)
    total, v = 0.0, next_var
    for _ in range(h):
        total = total + v
        v = omega + p * v
    return total


def garch_forecasts(r: pd.Series, h: int, min_train: int, refit: int,
                    fitter: Callable[[np.ndarray], tuple[float, float, float]]) -> tuple[pd.Series, list]:
    """Walk-forward GARCH(1,1) h-day variance. At each refit row t the parameters are estimated on
    r_0..r_t (all known at t) and then held fixed until the next refit; the variance recursion
    only ever uses returns up to the forecast date. Returns forecasts and a refit log of
    (refit row, last training row, omega, alpha, beta)."""
    x = r.to_numpy(dtype=float)
    out = np.full(len(x), np.nan)
    log = []
    for start in range(min_train, len(x), refit):
        omega, alpha, beta = fitter(x[:start + 1])
        p = alpha + beta
        s0 = omega / (1 - p) if p < 1 else float(np.var(x[:start + 1]))
        stop = min(start + refit, len(x))
        nv = garch_next_variance(x[:stop], omega, alpha, beta, s0)
        out[start:stop] = garch_h_sum(nv[start:stop], omega, alpha, beta, h)
        log.append((start, start, omega, alpha, beta))
    return pd.Series(out, index=r.index), log


# --- Return and direction models ---------------------------------------------------------------

def features(r: pd.Series, lam: float, seed_n: int, lags: int, vol_window: int) -> pd.DataFrame:
    """Pre-declared features known at t: the last `lags` daily returns, the trailing 5-day return,
    trailing realised volatility over `vol_window` days and the EWMA volatility."""
    cols = {f"r_lag{k}": r.shift(k) for k in range(lags)}
    cols["ret5"] = r.rolling(5).sum()
    cols["rv"] = np.sqrt((r ** 2).rolling(vol_window).mean())
    cols["ewma_sd"] = np.sqrt(ewma_variance(r, lam, seed_n))
    return pd.DataFrame(cols, index=r.index)


def _standardise(X: np.ndarray):
    mu, sd = X.mean(axis=0), X.std(axis=0, ddof=0)
    sd = np.where(sd > 0, sd, 1.0)
    return mu, sd


def fit_mean(X: np.ndarray, y: np.ndarray):
    """Historical drift: the mean of the training targets."""
    return float(y.mean())


def predict_mean(model, X: np.ndarray) -> np.ndarray:
    return np.full(len(X), model)


def fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float):
    """Ridge on standardised features, unpenalised intercept:
    b = (Z'Z + alpha I)^-1 Z'(y - ybar), intercept = ybar."""
    mu, sd = _standardise(X)
    Z = (X - mu) / sd
    b = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - y.mean()))
    return mu, sd, float(y.mean()), b


def predict_ridge(model, X: np.ndarray) -> np.ndarray:
    mu, sd, b0, b = model
    return b0 + ((X - mu) / sd) @ b


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float, max_iter: int = 50, tol: float = 1e-9):
    """L2-penalised logistic regression on standardised features (intercept unpenalised), fitted
    by Newton-Raphson."""
    mu, sd = _standardise(X)
    Z = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    w = np.zeros(Z.shape[1])
    pen = np.full(Z.shape[1], l2)
    pen[0] = 0.0
    for _ in range(max_iter):
        p = 1 / (1 + np.exp(-np.clip(Z @ w, -35, 35)))
        grad = Z.T @ (p - y) + pen * w
        hess = (Z * (p * (1 - p))[:, None]).T @ Z + np.diag(pen) + 1e-10 * np.eye(len(w))
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.max(np.abs(step)) < tol:
            break
    return mu, sd, w


def predict_logistic(model, X: np.ndarray) -> np.ndarray:
    """Probability that the forward return is up."""
    mu, sd, w = model
    Z = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    return 1 / (1 + np.exp(-np.clip(Z @ w, -35, 35)))


def walk_forward(X: pd.DataFrame, y: pd.Series, h: int, min_train: int, refit: int,
                 fit: Callable, predict: Callable) -> tuple[pd.Series, list[tuple[int, int]]]:
    """Expanding-window walk-forward. At refit row t, train on rows s <= t - h whose features and
    target exist; predict rows t .. t + refit - 1 with that model. Returns predictions and a log
    of (refit row, last training row) used to prove there is no look-ahead."""
    Xv, yv = X.to_numpy(dtype=float), y.to_numpy(dtype=float)
    ok_x = np.isfinite(Xv).all(axis=1)
    usable = ok_x & np.isfinite(yv)
    out = np.full(len(Xv), np.nan)
    log = []
    for start in range(min_train, len(Xv), refit):
        idx = np.flatnonzero(usable[:max(start - h + 1, 0)])
        if len(idx) < Xv.shape[1] + 2:
            continue
        model = fit(Xv[idx], yv[idx])
        rows = np.arange(start, min(start + refit, len(Xv)))
        rows = rows[ok_x[rows]]
        if len(rows):
            out[rows] = predict(model, Xv[rows])
        log.append((start, int(idx[-1])))
    return pd.Series(out, index=X.index), log


# --- Losses, bootstrap and verdict ---------------------------------------------------------------

def qlike(rv: np.ndarray, f: np.ndarray) -> np.ndarray:
    return np.log(f) + rv / f


def vol_abs_error(rv: np.ndarray, f: np.ndarray) -> np.ndarray:
    return np.abs(np.sqrt(rv) - np.sqrt(f))


def block_bootstrap_mean(d: np.ndarray, block: int, n_boot: int, seed: int,
                         conf: float) -> tuple[float, float, float]:
    """Mean of d and a moving-block bootstrap percentile interval. Each replicate joins
    ceil(n / block) blocks of `block` consecutive values drawn with replacement from the n - block + 1
    possible starts; its mean is the mean of those values."""
    d = np.asarray(d, dtype=float)
    n = len(d)
    block = max(1, min(block, n))
    k = int(np.ceil(n / block))
    csum = np.concatenate([[0.0], np.cumsum(d)])
    block_sums = csum[block:] - csum[:-block]  # sum of each block, by start position
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(block_sums), size=(n_boot, k))
    means = block_sums[starts].sum(axis=1) / (k * block)
    a = (1 - conf) / 2
    lo, hi = np.quantile(means, [a, 1 - a])
    return float(d.mean()), float(lo), float(hi)


def verdict(lo: float, hi: float) -> str:
    if hi < 0:
        return BEATS
    if lo > 0:
        return LOSES
    return INCONCLUSIVE


# --- Trading rule and equity curve ---------------------------------------------------------------

def equity_curve(r: pd.Series, position: pd.Series, cost: float) -> pd.Series:
    """Growth of 1 for a long/flat rule. position_t in {0, 1} is decided at the close of t and
    earns the simple return of t+1; each change of position costs `cost` (a decimal) of capital.
    Entering at the first decision counts as a trade. Cash earns nothing (simplification)."""
    pos = position.astype(float)
    nxt = np.expm1(r.shift(-1))  # simple return from t to t+1
    trades = pos.diff().abs()
    trades.iloc[0] = abs(pos.iloc[0])
    growth = (1 + pos * nxt) * (1 - cost * trades)
    growth = growth.iloc[:-1]  # the last decision has no next-day return yet
    growth.index = r.index[1:]  # labelled by the day the return is earned
    return growth.cumprod()


def curve_stats(curve: pd.Series, trading_days: int) -> dict:
    total = float(curve.iloc[-1] - 1)
    years = len(curve) / trading_days
    daily = curve.pct_change().fillna(curve.iloc[0] - 1)
    dd = curve / curve.cummax() - 1
    return {"total_return": total,
            "annual_return": float((1 + total) ** (1 / years) - 1) if years > 0 else float("nan"),
            "annual_vol": float(daily.std(ddof=1) * np.sqrt(trading_days)),
            "max_drawdown": float(dd.min())}


def headline(results: list[dict]) -> str:
    """One sentence counting verdicts across every comparison. Generated from the results only."""
    n = len(results)
    if n == 0:
        return "No comparisons were run."
    count = {v: sum(r["verdict"] == v for r in results) for v in (BEATS, LOSES, INCONCLUSIVE)}
    return (f"In this historical out-of-sample test, {count[BEATS]} of {n} model-versus-naive "
            f"comparisons had lower average loss than the naive baseline with the whole interval "
            f"below zero (\"{BEATS}\"), {count[LOSES]} had higher loss (\"{LOSES}\") and "
            f"{count[INCONCLUSIVE]} were {INCONCLUSIVE}. This describes past data only.")
